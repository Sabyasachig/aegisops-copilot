from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import cache_delete
from ..db.engine import get_db
from ..db.repository import create_incident
from ..models import Incident

router = APIRouter(tags=["webhooks"])


class GenericWebhookPayload(BaseModel):
    """Simple generic payload — use this for custom alerting tools or testing."""

    id: str
    title: str
    service: str
    severity: str = "high"
    owner: str = "on-call"
    summary: str = ""


class PagerDutyWebhookPayload(BaseModel):
    """Simplified PagerDuty v3 webhook envelope."""

    event: dict  # type: ignore[type-arg]


@router.post("/webhooks/generic", status_code=status.HTTP_201_CREATED)
async def webhook_generic(
    payload: GenericWebhookPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Ingest an incident from any generic alerting tool."""
    now = datetime.now(UTC)
    incident = Incident(
        id=payload.id,
        title=payload.title,
        service=payload.service,
        severity=payload.severity,  # type: ignore[arg-type]
        status="triage",
        owner=payload.owner,
        created_at=now,
        updated_at=now,
        summary=payload.summary,
        open_actions=[],
    )
    try:
        created = await create_incident(db, incident)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Incident already exists or DB error: {exc}",
        ) from exc
    await cache_delete("incidents:all")
    return {"incident_id": created.id, "status": "created"}


@router.post("/webhooks/pagerduty", status_code=status.HTTP_201_CREATED)
async def webhook_pagerduty(
    payload: PagerDutyWebhookPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Ingest a PagerDuty v3 *incident.triggered* event."""
    ev = payload.event
    if ev.get("event_type") != "incident.triggered":
        return {"status": "ignored", "reason": "non-trigger event type"}

    inc_data = ev.get("data", {})
    raw_id = str(inc_data.get("id", "unknown"))
    inc_id = f"PD-{raw_id[:8].upper()}"
    now = datetime.now(UTC)

    assignees = inc_data.get("assignees") or [{}]
    incident = Incident(
        id=inc_id,
        title=inc_data.get("title", "Untitled PagerDuty Incident"),
        service=(inc_data.get("service") or {}).get("name", "unknown"),
        severity=inc_data.get("severity", "high"),
        status="triage",
        owner=(assignees[0] or {}).get("summary", "on-call"),
        created_at=now,
        updated_at=now,
        summary=(inc_data.get("body") or {}).get("details", ""),
        open_actions=[],
    )
    try:
        created = await create_incident(db, incident)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Incident already exists or DB error: {exc}",
        ) from exc
    await cache_delete("incidents:all")
    return {"incident_id": created.id, "status": "created"}
