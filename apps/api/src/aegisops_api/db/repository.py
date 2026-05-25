from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun, Incident
from .orm_models import AgentRunRow, IncidentRow


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _row_to_incident(row: IncidentRow) -> Incident:
    return Incident(
        id=row.id,
        title=row.title,
        service=row.service,
        severity=row.severity,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        owner=row.owner,
        created_at=row.created_at,
        updated_at=row.updated_at,
        summary=row.summary,
        open_actions=list(row.open_actions or []),
    )


def _row_to_run(row: AgentRunRow) -> AgentRun:
    return AgentRun(
        id=row.id,
        incident_id=row.incident_id,
        agent_name=row.agent_name,
        status=row.status,  # type: ignore[arg-type]
        started_at=row.started_at,
        finished_at=row.finished_at,
        summary=row.summary,
        artifact_url=row.artifact_url,
    )


# ---------------------------------------------------------------------------
# Incident CRUD
# ---------------------------------------------------------------------------

async def list_incidents(db: AsyncSession) -> list[Incident]:
    result = await db.execute(
        select(IncidentRow).order_by(IncidentRow.created_at.desc())
    )
    return [_row_to_incident(r) for r in result.scalars()]


async def get_incident(db: AsyncSession, incident_id: str) -> Incident | None:
    row = await db.get(IncidentRow, incident_id)
    return _row_to_incident(row) if row else None


async def create_incident(db: AsyncSession, incident: Incident) -> Incident:
    row = IncidentRow(
        id=incident.id,
        title=incident.title,
        service=incident.service,
        severity=incident.severity,
        status=incident.status,
        owner=incident.owner,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        summary=incident.summary,
        open_actions=incident.open_actions,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _row_to_incident(row)


async def update_incident(
    db: AsyncSession,
    incident_id: str,
    *,
    status: str | None = None,
    summary: str | None = None,
    open_actions: list[str] | None = None,
) -> Incident | None:
    row = await db.get(IncidentRow, incident_id)
    if row is None:
        return None
    if status is not None:
        row.status = status
    if summary is not None:
        row.summary = summary
    if open_actions is not None:
        row.open_actions = open_actions
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return _row_to_incident(row)


# ---------------------------------------------------------------------------
# Agent run CRUD
# ---------------------------------------------------------------------------

async def list_runs_for_incident(db: AsyncSession, incident_id: str) -> list[AgentRun]:
    result = await db.execute(
        select(AgentRunRow)
        .where(AgentRunRow.incident_id == incident_id)
        .order_by(AgentRunRow.started_at.desc())
    )
    return [_row_to_run(r) for r in result.scalars()]


async def create_agent_run(
    db: AsyncSession,
    incident_id: str,
    agent_name: str,
    summary: str,
) -> AgentRun:
    row = AgentRunRow(
        id=f"RUN-{uuid4().hex[:8].upper()}",
        incident_id=incident_id,
        agent_name=agent_name,
        status="queued",
        summary=summary,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _row_to_run(row)


async def complete_agent_run(
    db: AsyncSession,
    run_id: str,
    summary: str,
    status: str = "done",
) -> AgentRun | None:
    result = await db.execute(
        select(AgentRunRow).where(AgentRunRow.id == run_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.status = status
    row.summary = summary
    row.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return _row_to_run(row)
