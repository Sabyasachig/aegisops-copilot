from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SeverityLevel = Literal["critical", "high", "medium", "low", "info"]
IncidentStatus = Literal["triage", "investigating", "mitigating", "resolved"]
RunStatus = Literal["queued", "running", "done", "blocked"]
LLMProvider = Literal["groq", "openai", "anthropic"]


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


class ProviderInfo(BaseModel):
    provider: LLMProvider
    model_name: str
    tracing_enabled: bool
