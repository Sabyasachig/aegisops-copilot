"""Unit tests for Pydantic models — no services required."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aegisops_api.models import (
    AgentRun,
    EnqueueResponse,
    Incident,
    TaskStatusResponse,
)

_NOW = datetime.now(tz=timezone.utc)


def _sample_incident(**kwargs) -> dict:
    return {
        "id": "INC-0001",
        "title": "Test incident",
        "service": "test-svc",
        "severity": "high",
        "status": "triage",
        "owner": "oncall-team",
        "created_at": _NOW,
        "updated_at": _NOW,
        "summary": "Something broke",
        **kwargs,
    }


class TestIncidentModel:
    def test_valid_incident(self) -> None:
        inc = Incident(**_sample_incident())
        assert inc.id == "INC-0001"

    def test_open_actions_defaults_to_empty(self) -> None:
        inc = Incident(**_sample_incident())
        assert inc.open_actions == []

    def test_invalid_severity_raises(self) -> None:
        with pytest.raises(ValidationError):
            Incident(**_sample_incident(severity="ultra-critical"))

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            Incident(**_sample_incident(status="unknown"))

    def test_open_actions_populated(self) -> None:
        inc = Incident(**_sample_incident(open_actions=["rollback deploy"]))
        assert inc.open_actions == ["rollback deploy"]


class TestAgentRunModel:
    def _sample(self, **kwargs) -> dict:
        return {
            "id": "RUN-0001",
            "incident_id": "INC-0001",
            "agent_name": "incident-ops",
            "status": "done",
            "started_at": _NOW,
            "summary": "All done",
            **kwargs,
        }

    def test_valid_run(self) -> None:
        run = AgentRun(**self._sample())
        assert run.id == "RUN-0001"

    def test_finished_at_optional(self) -> None:
        run = AgentRun(**self._sample())
        assert run.finished_at is None

    def test_finished_at_set(self) -> None:
        run = AgentRun(**self._sample(finished_at=_NOW))
        assert run.finished_at == _NOW

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            AgentRun(**self._sample(status="exploded"))


class TestEnqueueResponse:
    def test_status_is_queued(self) -> None:
        resp = EnqueueResponse(
            task_id="t-1",
            run_id="r-1",
            incident_id="INC-0001",
            poll_url="/api/tasks/t-1",
        )
        assert resp.status == "queued"


class TestTaskStatusResponse:
    def test_pending_state(self) -> None:
        resp = TaskStatusResponse(task_id="t-1", state="PENDING")
        assert resp.result is None
        assert resp.error is None

    def test_failure_state(self) -> None:
        resp = TaskStatusResponse(task_id="t-1", state="FAILURE", error="boom")
        assert resp.error == "boom"
