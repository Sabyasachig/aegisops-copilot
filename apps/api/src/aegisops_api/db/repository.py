from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..metrics import observe_agent_run_duration, observe_incident_mttr
from ..models import AgentRun, Incident
from .orm_models import AgentRunRow, IncidentRow, UserRow

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
    result = await db.execute(select(IncidentRow).order_by(IncidentRow.created_at.desc()))
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
    row.updated_at = datetime.now(UTC)

    if status == "resolved":
        mttr_seconds = (row.updated_at - row.created_at).total_seconds()
        observe_incident_mttr(mttr_seconds)

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
    result = await db.execute(select(AgentRunRow).where(AgentRunRow.id == run_id))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.status = status
    row.summary = summary
    row.finished_at = datetime.now(UTC)
    observe_agent_run_duration((row.finished_at - row.started_at).total_seconds())
    await db.commit()
    await db.refresh(row)
    return _row_to_run(row)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


async def get_user_by_username(db: AsyncSession, username: str) -> UserRow | None:
    result = await db.execute(select(UserRow).where(UserRow.username == username))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    username: str,
    hashed_password: str,
    role: str = "viewer",
) -> UserRow:
    row = UserRow(
        id=str(uuid4()),
        username=username,
        hashed_password=hashed_password,
        role=role,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_user_role(db: AsyncSession, user_id: str, role: str) -> None:
    row = await db.get(UserRow, user_id)
    if row is not None:
        row.role = role
        await db.commit()


async def delete_incident(db: AsyncSession, incident_id: str) -> bool:
    """Delete an incident and cascade-delete its runs. Returns True if found."""
    row = await db.get(IncidentRow, incident_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def get_run_by_id(db: AsyncSession, run_id: str) -> AgentRun | None:
    """Return the AgentRun for *run_id*, or ``None`` if not found."""
    result = await db.execute(select(AgentRunRow).where(AgentRunRow.id == run_id))
    row = result.scalar_one_or_none()
    return _row_to_run(row) if row else None


async def update_agent_run_status(
    db: AsyncSession,
    run_id: str,
    status: str,
) -> AgentRun | None:
    """Set the status of a run.  Stamps ``finished_at`` for terminal statuses."""
    result = await db.execute(select(AgentRunRow).where(AgentRunRow.id == run_id))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.status = status
    if status in ("done", "rejected"):
        row.finished_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return _row_to_run(row)
