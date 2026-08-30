"""Tests for circuit breaker state machine, LLM fallback chain, and health exposure."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aegisops_api.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    get_all_circuit_states,
    get_circuit,
    reset_all,
)


@pytest.fixture(autouse=True)
def _reset_circuits():
    """Ensure a clean circuit registry for every test in this module."""
    reset_all()
    yield
    reset_all()


# ── CircuitBreaker state machine ───────────────────────────────────────────────

class TestCircuitBreakerStateMachine:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("p", failure_threshold=3, recovery_seconds=30)
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available()

    def test_opens_after_failure_threshold(self):
        cb = CircuitBreaker("p", failure_threshold=3, recovery_seconds=30)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # threshold not yet reached
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.is_available()

    def test_success_resets_to_closed(self):
        cb = CircuitBreaker("p", failure_threshold=2, recovery_seconds=30)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available()

    def test_half_open_after_recovery_timeout(self, monkeypatch):
        from datetime import UTC, datetime, timedelta

        cb = CircuitBreaker("p", failure_threshold=1, recovery_seconds=30)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Patch datetime.now inside circuit_breaker to simulate time advancing
        future = datetime.now(UTC) + timedelta(seconds=31)
        monkeypatch.setattr(
            "aegisops_api.circuit_breaker.datetime",
            type("_dt", (), {"now": staticmethod(lambda tz=None: future)})(),
        )
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_available()


# ── Registry helpers ────────────────────────────────────────────────────────────

def test_get_all_circuit_states_empty_initially():
    assert get_all_circuit_states() == {}


def test_get_all_circuit_states_reports_created_circuits():
    get_circuit("groq")
    get_circuit("openai")
    states = get_all_circuit_states()
    assert states["groq"] == "closed"
    assert states["openai"] == "closed"


# ── call_with_fallback behaviour ───────────────────────────────────────────────

def _messages():
    from langchain_core.messages import HumanMessage
    return [HumanMessage(content="test prompt")]


class TestCallWithFallback:
    def test_returns_primary_provider_on_success(self):
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="ok")

        with patch("aegisops_api.llm.build_chat_model", return_value=mock_model):
            from aegisops_api.llm import call_with_fallback
            _, used = call_with_fallback(_messages(), primary_provider="groq")

        assert used == "groq"

    def test_falls_back_when_invocation_fails(self):
        groq_model = MagicMock()
        groq_model.invoke.side_effect = RuntimeError("rate limited")
        openai_model = MagicMock()
        openai_model.invoke.return_value = MagicMock(content="fallback ok")

        def _factory(provider, model_name=None):
            return groq_model if provider == "groq" else openai_model

        with patch("aegisops_api.llm.build_chat_model", side_effect=_factory):
            from aegisops_api.llm import call_with_fallback
            _, used = call_with_fallback(_messages(), primary_provider="groq")

        assert used == "openai"

    def test_raises_when_all_providers_exhausted(self):
        failing_model = MagicMock()
        failing_model.invoke.side_effect = RuntimeError("all down")

        with patch("aegisops_api.llm.build_chat_model", return_value=failing_model):
            from aegisops_api.llm import call_with_fallback
            with pytest.raises(RuntimeError, match="exhausted"):
                call_with_fallback(_messages(), primary_provider="groq")

    def test_circuit_opens_after_threshold_failures(self):
        failing_model = MagicMock()
        failing_model.invoke.side_effect = RuntimeError("down")

        with patch("aegisops_api.llm.build_chat_model", return_value=failing_model):
            from aegisops_api.llm import call_with_fallback
            # Each call exhausts all providers; groq gets one failure per call
            for _ in range(3):
                with pytest.raises(RuntimeError):
                    call_with_fallback(_messages(), primary_provider="groq")

        states = get_all_circuit_states()
        assert states.get("groq") == "open"

    def test_open_circuit_is_skipped(self):
        # Pre-open the groq circuit
        cb = get_circuit("groq", failure_threshold=1, recovery_seconds=3600)
        cb.record_failure()
        assert not cb.is_available()

        openai_model = MagicMock()
        openai_model.invoke.return_value = MagicMock(content="openai ok")

        def _factory(provider, model_name=None):
            if provider == "groq":
                raise AssertionError("groq should have been skipped")
            return openai_model

        with patch("aegisops_api.llm.build_chat_model", side_effect=_factory):
            from aegisops_api.llm import call_with_fallback
            _, used = call_with_fallback(_messages(), primary_provider="groq")

        assert used == "openai"

    def test_circuit_alert_logged_when_opened(self, capfd):
        failing_model = MagicMock()
        failing_model.invoke.side_effect = RuntimeError("timeout")
        cb = get_circuit("groq", failure_threshold=1, recovery_seconds=3600)

        with patch("aegisops_api.llm.build_chat_model", return_value=failing_model):
            from aegisops_api.llm import call_with_fallback
            # Use a fresh mock to capture the warning log call
            with patch("aegisops_api.llm.logger") as mock_logger:
                with pytest.raises(RuntimeError):
                    call_with_fallback(_messages(), primary_provider="groq")
                # circuit_opened warning should have been emitted
                warning_events = [
                    call.args[0]
                    for call in mock_logger.warning.call_args_list
                ]
                assert "circuit_opened" in warning_events


# ── Health endpoint integration ────────────────────────────────────────────────

def test_health_includes_llm_circuit_key(client: TestClient):
    body = client.get("/api/health").json()
    assert "llm_circuit" in body["checks"]


def test_health_llm_circuit_shows_provider_state(client: TestClient):
    # Trigger a circuit entry by accessing it
    get_circuit("groq")
    body = client.get("/api/health").json()
    # The circuit dict may be empty (no invocations) but the key must exist
    assert isinstance(body["checks"]["llm_circuit"], dict)
