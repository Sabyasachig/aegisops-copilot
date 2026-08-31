"""Tests for @tool-decorated LangChain tool integrations (Issue #12).

Each tool gracefully degrades to a dry-run message when its integration is not
configured, so these tests run without any external services.

Tools under test
----------------
- k8s_get_pod_status
- datadog_get_metric_snapshot
- slack_post_incident_summary
- jira_create_incident_ticket
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(**overrides) -> MagicMock:
    """Return a Settings-like mock with tool integration attributes."""
    m = MagicMock()
    # Defaults — all integrations disabled
    m.k8s_enabled = False
    m.datadog_api_key = None
    m.datadog_app_key = None
    m.datadog_site = "datadoghq.com"
    m.slack_webhook_url = None
    m.slack_default_channel = "#incidents"
    m.jira_url = None
    m.jira_email = None
    m.jira_api_token = None
    m.jira_project_key = None
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------------------
# ALL_TOOLS registry
# ---------------------------------------------------------------------------


def test_all_tools_registered() -> None:
    from aegisops_api.tools import ALL_TOOLS

    assert len(ALL_TOOLS) == 4
    names = {t.name for t in ALL_TOOLS}
    assert "k8s_get_pod_status" in names
    assert "datadog_get_metric_snapshot" in names
    assert "slack_post_incident_summary" in names
    assert "jira_create_incident_ticket" in names


# ---------------------------------------------------------------------------
# k8s_get_pod_status
# ---------------------------------------------------------------------------


def test_k8s_tool_dry_run_when_disabled() -> None:
    from aegisops_api.tools import k8s_get_pod_status

    with patch("aegisops_api.tools.get_settings", return_value=_mock_settings(k8s_enabled=False)):
        result = k8s_get_pod_status.invoke({"service": "payments"})

    assert "dry-run" in result.lower()
    assert "kubectl" in result


def test_k8s_tool_calls_subprocess_when_enabled() -> None:
    from aegisops_api.tools import k8s_get_pod_status

    mock_settings = _mock_settings(k8s_enabled=True)
    pod_output = b"payments-pod-abc   1/1   Running   0   2m"
    with patch("aegisops_api.tools.get_settings", return_value=mock_settings), \
         patch("subprocess.check_output", return_value=pod_output) as mock_sub:
        result = k8s_get_pod_status.invoke({"service": "payments", "namespace": "prod"})

    mock_sub.assert_called_once()
    assert "Running" in result


def test_k8s_tool_handles_subprocess_error() -> None:
    from aegisops_api.tools import k8s_get_pod_status

    mock_settings = _mock_settings(k8s_enabled=True)
    with patch("aegisops_api.tools.get_settings", return_value=mock_settings), \
         patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(1, "kubectl", b"Error")):
        result = k8s_get_pod_status.invoke({"service": "payments"})

    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# datadog_get_metric_snapshot
# ---------------------------------------------------------------------------


def test_datadog_tool_dry_run_without_api_key() -> None:
    from aegisops_api.tools import datadog_get_metric_snapshot

    with patch("aegisops_api.tools.get_settings", return_value=_mock_settings()):
        result = datadog_get_metric_snapshot.invoke({"service": "payments"})

    assert "dry-run" in result.lower()


def test_datadog_tool_queries_api_when_configured() -> None:
    import httpx

    from aegisops_api.tools import datadog_get_metric_snapshot

    mock_settings = _mock_settings(
        datadog_api_key="test-api-key",
        datadog_app_key="test-app-key",
        datadog_site="datadoghq.com",
    )
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "series": [{"pointlist": [[1000000, 42.5], [1000060, 45.0]]}]
    }
    with patch("aegisops_api.tools.get_settings", return_value=mock_settings), \
         patch("httpx.get", return_value=mock_resp) as mock_get:
        result = datadog_get_metric_snapshot.invoke({"service": "payments", "window_minutes": 30})

    mock_get.assert_called_once()
    assert "43" in result or "43.75" in result or "%" in result


def test_datadog_tool_handles_empty_series() -> None:
    from aegisops_api.tools import datadog_get_metric_snapshot

    mock_settings = _mock_settings(datadog_api_key="test-api-key")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"series": []}
    with patch("aegisops_api.tools.get_settings", return_value=mock_settings), \
         patch("httpx.get", return_value=mock_resp):
        result = datadog_get_metric_snapshot.invoke({"service": "payments"})

    assert "no metric data" in result.lower()


# ---------------------------------------------------------------------------
# slack_post_incident_summary
# ---------------------------------------------------------------------------


def test_slack_tool_dry_run_without_webhook() -> None:
    from aegisops_api.tools import slack_post_incident_summary

    with patch("aegisops_api.tools.get_settings", return_value=_mock_settings()):
        result = slack_post_incident_summary.invoke({"channel": "#incidents", "message": "Test"})

    assert "dry-run" in result.lower()


def test_slack_tool_posts_when_configured() -> None:
    from aegisops_api.tools import slack_post_incident_summary

    mock_settings = _mock_settings(slack_webhook_url="https://hooks.slack.com/test")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    with patch("aegisops_api.tools.get_settings", return_value=mock_settings), \
         patch("httpx.post", return_value=mock_resp) as mock_post:
        result = slack_post_incident_summary.invoke(
            {"channel": "#incidents", "message": "API is down — P1"}
        )

    mock_post.assert_called_once()
    assert "successfully" in result.lower()


def test_slack_tool_handles_http_error() -> None:
    import httpx

    from aegisops_api.tools import slack_post_incident_summary

    mock_settings = _mock_settings(slack_webhook_url="https://hooks.slack.com/test")
    with patch("aegisops_api.tools.get_settings", return_value=mock_settings), \
         patch("httpx.post", side_effect=httpx.HTTPError("connection refused")):
        result = slack_post_incident_summary.invoke({"channel": "#incidents", "message": "Test"})

    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# jira_create_incident_ticket
# ---------------------------------------------------------------------------


def test_jira_tool_dry_run_without_config() -> None:
    from aegisops_api.tools import jira_create_incident_ticket

    with patch("aegisops_api.tools.get_settings", return_value=_mock_settings()):
        result = jira_create_incident_ticket.invoke(
            {"summary": "Post-incident review", "description": "Details here."}
        )

    assert "dry-run" in result.lower()


def test_jira_tool_creates_ticket_when_configured() -> None:
    from aegisops_api.tools import jira_create_incident_ticket

    mock_settings = _mock_settings(
        jira_url="https://company.atlassian.net",
        jira_email="bot@company.com",
        jira_api_token="secret-token",
        jira_project_key="OPS",
    )
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"key": "OPS-42"}
    with patch("aegisops_api.tools.get_settings", return_value=mock_settings), \
         patch("httpx.post", return_value=mock_resp) as mock_post:
        result = jira_create_incident_ticket.invoke(
            {"summary": "Post-incident review", "description": "Details."}
        )

    mock_post.assert_called_once()
    assert "OPS-42" in result
    assert "atlassian.net" in result


def test_jira_tool_handles_http_error() -> None:
    import httpx

    from aegisops_api.tools import jira_create_incident_ticket

    mock_settings = _mock_settings(
        jira_url="https://company.atlassian.net",
        jira_email="bot@company.com",
        jira_api_token="secret-token",
        jira_project_key="OPS",
    )
    with patch("aegisops_api.tools.get_settings", return_value=mock_settings), \
         patch("httpx.post", side_effect=httpx.HTTPError("timeout")):
        result = jira_create_incident_ticket.invoke(
            {"summary": "Post-incident review", "description": "Details."}
        )

    assert "error" in result.lower()
