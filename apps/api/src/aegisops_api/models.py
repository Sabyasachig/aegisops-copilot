from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SeverityLevel = Literal["critical", "high", "medium", "low", "info"]
IncidentStatus = Literal["triage", "investigating", "mitigating", "resolved"]
RunStatus = Literal["queued", "running", "done", "blocked", "needs_human", "rejected"]
LLMProvider = Literal["groq", "openai", "anthropic"]
UserRole = Literal["viewer", "operator", "admin"]


class Incident(BaseModel):
    id: str
    title: str
    service: str
    severity: SeverityLevel
    status: IncidentStatus
    owner: str
    created_at: datetime
    updated_at: datetime
    summary: str
    open_actions: list[str] = Field(default_factory=list)


class AgentRun(BaseModel):
    id: str
    incident_id: str
    agent_name: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    summary: str
    artifact_url: str | None = None


class ExecuteIncidentRequest(BaseModel):
    incident_id: str


class ExecuteIncidentResponse(BaseModel):
    incident_id: str
    status: RunStatus
    graph_run_id: str
    summary: str
    next_action: str
    run_id: str


class ApproveRunRequest(BaseModel):
    """Request body for approving a paused run (no required fields)."""


class RejectRunRequest(BaseModel):
    reason: str = ""


class ProviderInfo(BaseModel):
    provider: LLMProvider
    model_name: str
    tracing_enabled: bool


# ── Async task queue models ───────────────────────────────────────────────────

TaskState = Literal["PENDING", "STARTED", "SUCCESS", "FAILURE", "RETRY", "REVOKED"]


class EnqueueResponse(BaseModel):
    """Returned immediately (202) after enqueuing an incident workflow run."""

    task_id: str
    run_id: str
    incident_id: str
    status: Literal["queued"] = "queued"
    poll_url: str


class TaskStatusResponse(BaseModel):
    """Returned by GET /api/tasks/{task_id}."""

    task_id: str
    state: TaskState
    # Populated once state == "SUCCESS"
    result: ExecuteIncidentResponse | None = None
    # Populated once state == "FAILURE"
    error: str | None = None
