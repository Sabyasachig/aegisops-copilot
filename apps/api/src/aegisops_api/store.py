from __future__ import annotations

from datetime import datetime, timezone
from itertools import count
from uuid import uuid4

from .models import AgentRun, Incident, IncidentStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


incidents: list[Incident] = [
    Incident(
        id="INC-2048",
        title="Event ingest latency climbed 5x after deploy",
        service="event-ingest",
        severity="high",
        status="triage",
        owner="on-call-platform",
        created_at=_utcnow(),
        updated_at=_utcnow(),
        summary="Consumer lag and retry depth increased immediately after the release window.",
        open_actions=["Inspect deploy diff", "Check broker saturation", "Notify the owning team"]
    ),
    Incident(
        id="INC-2081",
        title="Billing callbacks are timing out for a subset of tenants",
        service="billing",
        severity="critical",
        status="investigating",
        owner="revenue-engineering",
        created_at=_utcnow(),
        updated_at=_utcnow(),
        summary="Payment retries remain healthy, but the callback queue is backing up.",
        open_actions=["Pause nonessential retries", "Inspect ledger consistency", "Review gateway status"]
    ),
    Incident(
        id="INC-2093",
        title="SSO sign-in error rate exceeded threshold",
        service="auth",
        severity="medium",
        status="mitigating",
        owner="identity-platform",
        created_at=_utcnow(),
        updated_at=_utcnow(),
        summary="A recent config change appears to have affected token validation for older clients.",
        open_actions=["Verify identity provider status", "Compare config revisions", "Restore last known good key"]
    )
]

agent_runs: list[AgentRun] = [
    AgentRun(
        id="RUN-1001",
        incident_id="INC-2048",
        agent_name="incident-triage",
        status="done",
        started_at=_utcnow(),
        finished_at=_utcnow(),
        summary="Confirmed the latency spike is most likely tied to the release window and a consumer lag burst.",
        artifact_url=None
    ),
    AgentRun(
        id="RUN-1002",
        incident_id="INC-2081",
        agent_name="mitigation-draft",
        status="running",
        started_at=_utcnow(),
        finished_at=None,
        summary="Collecting evidence for billing callback degradation.",
        artifact_url=None
    )
]

_run_counter = count(2000)


def list_incidents() -> list[Incident]:
    return incidents


def get_incident(incident_id: str) -> Incident | None:
    return next((incident for incident in incidents if incident.id == incident_id), None)


def list_runs_for_incident(incident_id: str) -> list[AgentRun]:
    return sorted(
        [run for run in agent_runs if run.incident_id == incident_id],
        key=lambda run: run.started_at,
        reverse=True,
    )


def create_agent_run(incident_id: str, agent_name: str, summary: str) -> AgentRun:
    run = AgentRun(
        id=f"RUN-{next(_run_counter)}",
        incident_id=incident_id,
        agent_name=agent_name,
        status="queued",
        started_at=_utcnow(),
        finished_at=None,
        summary=summary,
        artifact_url=None,
    )
    agent_runs.insert(0, run)
    return run


def complete_agent_run(run_id: str, summary: str, artifact_url: str | None = None) -> AgentRun:
    for run in agent_runs:
        if run.id == run_id:
            run.status = "done"
            run.finished_at = _utcnow()
            run.summary = summary
            run.artifact_url = artifact_url
            return run
    raise ValueError(f"Run {run_id} was not found.")


def update_incident(
    incident_id: str,
    *,
    status: IncidentStatus | None = None,
    summary: str | None = None,
    open_actions: list[str] | None = None,
) -> Incident:
    incident = get_incident(incident_id)
    if incident is None:
        raise ValueError(f"Incident {incident_id} was not found.")

    if status is not None:
        incident.status = status  # type: ignore[assignment]
    if summary is not None:
        incident.summary = summary
    if open_actions is not None:
        incident.open_actions = open_actions
    incident.updated_at = _utcnow()
    return incident
