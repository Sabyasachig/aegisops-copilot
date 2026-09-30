from __future__ import annotations

import hashlib
import hmac as _hmac
import secrets
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import cache_delete
from ..db.engine import get_db
from ..db.repository import create_incident
from ..models import Incident
from ..settings import get_settings

router = APIRouter(tags=["webhooks"])


# ---------------------------------------------------------------------------
# HMAC helpers
# ---------------------------------------------------------------------------


def _compute_hmac_sha256(secret: str, data: bytes) -> str:
    return _hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()


def _verify_pagerduty_signature(raw_body: bytes, header: str, secret: str) -> bool:
    """PagerDuty v3: ``X-PagerDuty-Signature: v1=<hex>[,v1=<hex>]``.

    Any valid signature in the comma-separated list is accepted.
    """
    expected = _compute_hmac_sha256(secret, raw_body)
    for token in header.split(","):
        token = token.strip()
        if token.startswith("v1="):
            if secrets.compare_digest(expected, token[3:]):
                return True
    return False


def _verify_generic_signature(raw_body: bytes, header: str, secret: str) -> bool:
    """Generic format: ``X-Webhook-Signature: sha256=<hex>``."""
    expected = _compute_hmac_sha256(secret, raw_body)
    provided = header.split("=", 1)[-1] if "=" in header else header
    return secrets.compare_digest(expected, provided.strip())


def _require_signature(
    raw_body: bytes,
    signature: str | None,
    secret: str,
    *,
    style: Literal["pagerduty", "generic"],
) -> None:
    """Raise HTTP 403 if *signature* is absent or does not match *secret*.

    This uses a constant-time comparison to prevent timing-based attacks.
    """
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing webhook signature header",
        )
    verify = _verify_pagerduty_signature if style == "pagerduty" else _verify_generic_signature
    if not verify(raw_body, signature, secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        )


# ---------------------------------------------------------------------------
# Payload models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/webhooks/generic", status_code=status.HTTP_201_CREATED)
async def webhook_generic(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Ingest an incident from any generic alerting tool.

    When ``AIOPS_WEBHOOK_SECRET`` is set, the request must include an
    ``X-Webhook-Signature: sha256=<hmac-hex>`` header computed over the raw
    request body using HMAC-SHA256.
    """
    raw_body = await request.body()
    settings = get_settings()
    if settings.webhook_secret:
        _require_signature(
            raw_body,
            request.headers.get("x-webhook-signature"),
            settings.webhook_secret,
            style="generic",
        )

    try:
        payload = GenericWebhookPayload.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

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
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Ingest a PagerDuty v3 *incident.triggered* event.

    When ``AIOPS_WEBHOOK_SECRET`` is set, the request must include an
    ``X-PagerDuty-Signature: v1=<hmac-hex>`` header computed over the raw
    request body using HMAC-SHA256.
    """
    raw_body = await request.body()
    settings = get_settings()
    if settings.webhook_secret:
        _require_signature(
            raw_body,
            request.headers.get("x-pagerduty-signature"),
            settings.webhook_secret,
            style="pagerduty",
        )

    try:
        payload = PagerDutyWebhookPayload.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

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


# ---------------------------------------------------------------------------
# OpsGenie v2 webhook
# ---------------------------------------------------------------------------


class OpsGenieWebhookPayload(BaseModel):
    """Simplified OpsGenie v2 webhook envelope for ``Create`` alert actions."""

    action: str
    alert: dict  # type: ignore[type-arg]


# OpsGenie priority (P1–P5) → internal severity mapping.
_OPSGENIE_PRIORITY_MAP: dict[str, str] = {
    "P1": "critical",
    "P2": "high",
    "P3": "medium",
    "P4": "low",
    "P5": "info",
}


def _map_opsgenie_priority(priority: str | None) -> str:
    if not priority:
        return "high"
    return _OPSGENIE_PRIORITY_MAP.get(priority.upper(), "high")


@router.post("/webhooks/opsgenie", status_code=status.HTTP_201_CREATED)
async def webhook_opsgenie(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Ingest an OpsGenie v2 ``Create`` alert webhook.

    When ``AIOPS_WEBHOOK_SECRET`` is set, the request must include an
    ``X-Webhook-Signature: sha256=<hmac-hex>`` header computed over the raw
    request body using HMAC-SHA256.
    """
    raw_body = await request.body()
    settings = get_settings()
    if settings.webhook_secret:
        _require_signature(
            raw_body,
            request.headers.get("x-webhook-signature"),
            settings.webhook_secret,
            style="generic",
        )

    try:
        payload = OpsGenieWebhookPayload.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if payload.action.lower() != "create":
        return {"status": "ignored", "reason": f"non-create action: {payload.action}"}

    alert = payload.alert or {}
    raw_id = str(alert.get("alertId") or alert.get("id") or "unknown")
    inc_id = f"OG-{raw_id[:8].upper()}"
    now = datetime.now(UTC)

    tags = alert.get("tags") or []
    service = "unknown"
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and tag.lower().startswith("service:"):
                service = tag.split(":", 1)[1].strip() or "unknown"
                break
    service = alert.get("entity") or service

    incident = Incident(
        id=inc_id,
        title=alert.get("message", "Untitled OpsGenie Alert"),
        service=service,
        severity=_map_opsgenie_priority(alert.get("priority")),  # type: ignore[arg-type]
        status="triage",
        owner=alert.get("owner") or "on-call",
        created_at=now,
        updated_at=now,
        summary=alert.get("description", ""),
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


# ---------------------------------------------------------------------------
# Prometheus Alertmanager webhook
# ---------------------------------------------------------------------------


class AlertmanagerWebhookPayload(BaseModel):
    """Prometheus Alertmanager v4 webhook envelope."""

    version: str | None = None
    status: str
    alerts: list[dict]  # type: ignore[type-arg]
    groupLabels: dict = {}  # noqa: N815  (Alertmanager uses camelCase on the wire)
    commonLabels: dict = {}  # noqa: N815
    commonAnnotations: dict = {}  # noqa: N815


# Alertmanager severity labels → internal severity mapping.
_ALERTMANAGER_SEVERITY_MAP: dict[str, str] = {
    "critical": "critical",
    "page": "critical",
    "error": "high",
    "high": "high",
    "warning": "medium",
    "warn": "medium",
    "info": "info",
    "low": "low",
    "none": "info",
}


def _map_alertmanager_severity(label: str | None) -> str:
    if not label:
        return "medium"
    return _ALERTMANAGER_SEVERITY_MAP.get(label.lower(), "medium")


@router.post("/webhooks/alertmanager", status_code=status.HTTP_201_CREATED)
async def webhook_alertmanager(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:  # type: ignore[type-arg]
    """Ingest a Prometheus Alertmanager webhook.

    Only ``status=firing`` payloads create incidents; ``resolved`` payloads are
    acknowledged and skipped (Alertmanager retries otherwise). When
    ``AIOPS_WEBHOOK_SECRET`` is set, the request must include an
    ``X-Webhook-Signature: sha256=<hmac-hex>`` header computed over the raw
    request body using HMAC-SHA256.
    """
    raw_body = await request.body()
    settings = get_settings()
    if settings.webhook_secret:
        _require_signature(
            raw_body,
            request.headers.get("x-webhook-signature"),
            settings.webhook_secret,
            style="generic",
        )

    try:
        payload = AlertmanagerWebhookPayload.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if payload.status.lower() != "firing":
        return {"status": "ignored", "reason": f"non-firing status: {payload.status}"}
    if not payload.alerts:
        return {"status": "ignored", "reason": "no alerts in payload"}

    first_alert = payload.alerts[0]
    labels = {**payload.commonLabels, **first_alert.get("labels", {})}
    annotations = {**payload.commonAnnotations, **first_alert.get("annotations", {})}

    fingerprint = str(first_alert.get("fingerprint") or labels.get("alertname") or "unknown")
    inc_id = f"AM-{fingerprint[:8].upper()}"
    now = datetime.now(UTC)

    incident = Incident(
        id=inc_id,
        title=annotations.get("summary")
        or labels.get("alertname", "Untitled Alertmanager Alert"),
        service=labels.get("service")
        or labels.get("job")
        or labels.get("instance", "unknown"),
        severity=_map_alertmanager_severity(labels.get("severity")),  # type: ignore[arg-type]
        status="triage",
        owner=labels.get("team") or labels.get("owner") or "on-call",
        created_at=now,
        updated_at=now,
        summary=annotations.get("description") or annotations.get("summary", ""),
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
