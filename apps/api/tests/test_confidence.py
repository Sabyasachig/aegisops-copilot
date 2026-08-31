"""Tests for Issue #15 — Confidence Scoring & Auto-Escalation.

Covers:
- _assess_confidence: JSON parsing, fallback to 0.5, clamping
- settings: default threshold + env override
- complete_agent_run: persists confidence column
- run_incident_workflow: status is needs_human when confidence < threshold;
  Slack/Jira are skipped on low confidence and called on high confidence
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_incident():
    from aegisops_api.models import Incident

    return Incident(
        id="INC-15-TEST",
        title="Payments API 500s",
        service="payments",
        severity="high",
        status="triage",
        owner="sre-team",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        summary="Error rate spiked to 10%.",
    )


def _fake_llm_response(content: str = "Analysis complete."):
    r = MagicMock()
    r.content = content
    r.response_metadata = {}
    r.usage_metadata = {}
    return r


def _fake_call(messages, provider, model_name):
    return _fake_llm_response(), provider


# ---------------------------------------------------------------------------
# _assess_confidence — unit tests (no DB, no graph)
# ---------------------------------------------------------------------------


def test_assess_confidence_parses_valid_json() -> None:
    from aegisops_api import agents

    mock_resp = _fake_llm_response('{"confidence": 0.85, "reason": "Strong evidence."}')
    with patch.object(agents, "call_with_fallback", return_value=(mock_resp, "groq")):
        score = agents._assess_confidence(
            evidence="Error rate 10%", response_draft="Roll back deploy.",
            provider="groq", model_name=None,
        )
    assert score == 0.85


def test_assess_confidence_defaults_to_half_on_no_json() -> None:
    from aegisops_api import agents

    mock_resp = _fake_llm_response("I am uncertain, cannot determine confidence.")
    with patch.object(agents, "call_with_fallback", return_value=(mock_resp, "groq")):
        score = agents._assess_confidence(
            evidence="E", response_draft="D", provider="groq", model_name=None,
        )
    assert score == 0.5


def test_assess_confidence_defaults_to_half_on_llm_error() -> None:
    from aegisops_api import agents

    with patch.object(agents, "call_with_fallback", side_effect=RuntimeError("LLM down")):
        score = agents._assess_confidence(
            evidence="E", response_draft="D", provider="groq", model_name=None,
        )
    assert score == 0.5


def test_assess_confidence_clamps_above_one() -> None:
    from aegisops_api import agents

    mock_resp = _fake_llm_response('{"confidence": 1.5, "reason": "Very sure."}')
    with patch.object(agents, "call_with_fallback", return_value=(mock_resp, "groq")):
        score = agents._assess_confidence(
            evidence="E", response_draft="D", provider="groq", model_name=None,
        )
    assert score == 1.0


def test_assess_confidence_clamps_below_zero() -> None:
    from aegisops_api import agents

    mock_resp = _fake_llm_response('{"confidence": -0.2, "reason": "No idea."}')
    with patch.object(agents, "call_with_fallback", return_value=(mock_resp, "groq")):
        score = agents._assess_confidence(
            evidence="E", response_draft="D", provider="groq", model_name=None,
        )
    assert score == 0.0


def test_assess_confidence_handles_malformed_json() -> None:
    from aegisops_api import agents

    mock_resp = _fake_llm_response('{"confidence": "not-a-float"}')
    with patch.object(agents, "call_with_fallback", return_value=(mock_resp, "groq")):
        # float("not-a-float") raises → falls back to 0.5
        score = agents._assess_confidence(
            evidence="E", response_draft="D", provider="groq", model_name=None,
        )
    assert score == 0.5


# ---------------------------------------------------------------------------
# settings — confidence_threshold
# ---------------------------------------------------------------------------


def test_confidence_threshold_default() -> None:
    from aegisops_api.settings import Settings

    s = Settings()
    assert s.confidence_threshold == 0.6


def test_confidence_threshold_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AIOPS_CONFIDENCE_THRESHOLD", "0.75")
    from aegisops_api.settings import Settings

    s = Settings()
    assert abs(s.confidence_threshold - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# complete_agent_run — stores confidence
# ---------------------------------------------------------------------------


def test_complete_agent_run_stores_confidence() -> None:
    from aegisops_api.db import repository
    from aegisops_api.db.orm_models import AgentRunRow

    row = AgentRunRow(
        id="RUN-CONF01",
        incident_id="INC-15-TEST",
        agent_name="aegisops",
        status="running",
        summary="",
        started_at=datetime.now(UTC),
    )
    captured = {}

    async def _fake_execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = row
        return result

    async def _fake_commit():
        captured["confidence"] = row.confidence

    async def _fake_refresh(_row):
        pass

    db = MagicMock()
    db.execute = _fake_execute
    db.commit = _fake_commit
    db.refresh = _fake_refresh

    async def _run():
        return await repository.complete_agent_run(db, "RUN-CONF01", "done", confidence=0.78)

    asyncio.run(_run())
    assert abs(captured["confidence"] - 0.78) < 1e-9


def test_complete_agent_run_accepts_none_confidence() -> None:
    from aegisops_api.db import repository
    from aegisops_api.db.orm_models import AgentRunRow

    row = AgentRunRow(
        id="RUN-CONF02",
        incident_id="INC-15-TEST",
        agent_name="aegisops",
        status="running",
        summary="",
        started_at=datetime.now(UTC),
    )

    async def _fake_execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = row
        return result

    db = MagicMock()
    db.execute = _fake_execute
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def _run():
        return await repository.complete_agent_run(db, "RUN-CONF02", "done", confidence=None)

    result = asyncio.run(_run())
    assert result.confidence is None


# ---------------------------------------------------------------------------
# run_incident_workflow — status override based on confidence
# ---------------------------------------------------------------------------


def _run_workflow_with_confidence(confidence_score: float):
    """Run the full graph with all LLM calls mocked; inject a fixed confidence score."""
    from aegisops_api import agents

    with patch.object(agents, "call_with_fallback", side_effect=_fake_call), \
         patch.object(agents, "interrupt", return_value=True), \
         patch.object(agents, "k8s_get_pod_status",
                      MagicMock(invoke=lambda _: "k8s: no pods")), \
         patch.object(agents, "datadog_get_metric_snapshot",
                      MagicMock(invoke=lambda _: "dd: no metrics")), \
         patch.object(agents, "_assess_confidence", return_value=confidence_score), \
         patch.object(agents, "slack_post_incident_summary",
                      MagicMock(invoke=lambda _: "slack-ok")), \
         patch.object(agents, "jira_create_incident_ticket",
                      MagicMock(invoke=lambda _: "JIRA-99")):
        return agents.run_incident_workflow(_make_incident(), provider="groq", model_name=None)


def test_workflow_done_when_high_confidence() -> None:
    result = _run_workflow_with_confidence(0.9)
    assert result["status"] == "done"
    assert result.get("confidence") == 0.9


def test_workflow_needs_human_when_low_confidence() -> None:
    result = _run_workflow_with_confidence(0.3)
    assert result["status"] == "needs_human"
    assert result.get("confidence") == 0.3


def test_workflow_needs_human_at_exactly_threshold() -> None:
    """Confidence equal to threshold should NOT escalate (>= check)."""
    result = _run_workflow_with_confidence(0.6)
    assert result["status"] == "done"


def test_workflow_low_confidence_skips_slack_and_jira() -> None:
    from aegisops_api import agents

    called_slack = []
    called_jira = []

    with patch.object(agents, "call_with_fallback", side_effect=_fake_call), \
         patch.object(agents, "interrupt", return_value=True), \
         patch.object(agents, "k8s_get_pod_status",
                      MagicMock(invoke=lambda _: "k8s: ok")), \
         patch.object(agents, "datadog_get_metric_snapshot",
                      MagicMock(invoke=lambda _: "dd: ok")), \
         patch.object(agents, "_assess_confidence", return_value=0.2), \
         patch.object(agents, "slack_post_incident_summary",
                      MagicMock(invoke=lambda _: called_slack.append(1) or "ok")), \
         patch.object(agents, "jira_create_incident_ticket",
                      MagicMock(invoke=lambda _: called_jira.append(1) or "ok")):
        agents.run_incident_workflow(_make_incident(), provider="groq", model_name=None)

    assert len(called_slack) == 0, "Slack should NOT be called on low confidence"
    assert len(called_jira) == 0, "Jira should NOT be called on low confidence"


def test_workflow_high_confidence_calls_slack_and_jira() -> None:
    from aegisops_api import agents

    called_slack = []
    called_jira = []

    with patch.object(agents, "call_with_fallback", side_effect=_fake_call), \
         patch.object(agents, "interrupt", return_value=True), \
         patch.object(agents, "k8s_get_pod_status",
                      MagicMock(invoke=lambda _: "k8s: ok")), \
         patch.object(agents, "datadog_get_metric_snapshot",
                      MagicMock(invoke=lambda _: "dd: ok")), \
         patch.object(agents, "_assess_confidence", return_value=0.95), \
         patch.object(agents, "slack_post_incident_summary",
                      MagicMock(invoke=lambda _: called_slack.append(1) or "posted")), \
         patch.object(agents, "jira_create_incident_ticket",
                      MagicMock(invoke=lambda _: called_jira.append(1) or "JIRA-1")):
        agents.run_incident_workflow(_make_incident(), provider="groq", model_name=None)

    assert len(called_slack) == 1, "Slack should be called on high confidence"
    assert len(called_jira) == 1, "Jira should be called on high confidence"
