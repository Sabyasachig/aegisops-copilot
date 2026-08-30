from __future__ import annotations

import structlog

from aegisops_api.logging_config import bind_log_context, clear_log_context, should_use_json_logs
from aegisops_api.settings import Settings


def test_should_use_json_logs_in_production_auto_mode() -> None:
    settings = Settings(environment="production", log_format="auto")
    assert should_use_json_logs(settings) is True


def test_should_use_console_logs_in_development_auto_mode() -> None:
    settings = Settings(environment="development", log_format="auto")
    assert should_use_json_logs(settings) is False


def test_explicit_log_format_overrides_environment() -> None:
    assert should_use_json_logs(Settings(environment="development", log_format="json")) is True
    assert should_use_json_logs(Settings(environment="production", log_format="console")) is False


def test_bind_log_context_binds_only_non_empty_fields() -> None:
    clear_log_context()
    bind_log_context(incident_id="INC-1001", run_id="run-xyz", user_id="admin", request_id="r1")

    context = structlog.contextvars.get_contextvars()
    assert context["incident_id"] == "INC-1001"
    assert context["run_id"] == "run-xyz"
    assert context["user_id"] == "admin"
    assert context["request_id"] == "r1"

    clear_log_context()
    assert structlog.contextvars.get_contextvars() == {}
