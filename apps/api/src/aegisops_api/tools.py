"""LangChain @tool-decorated integrations for real-system investigation and response.

Each tool gracefully degrades to a dry-run message when its credentials are not
configured, so the workflow still runs in dev/test environments without external
dependencies.

Tools
-----
- k8s_get_pod_status          — kubectl get pods for the affected service
- datadog_get_metric_snapshot — CPU/error-rate snapshot from Datadog
- slack_post_incident_summary — post a message to a Slack channel via webhook
- jira_create_incident_ticket — create a post-incident Jira task

Usage in graph
--------------
These tools are registered on the LangGraph graph via ``ToolNode(ALL_TOOLS)``.
They are also invoked directly inside the ``gather_evidence`` and
``package_outcome`` nodes during the current phase; future phases can wire
them through an LLM-directed ReAct loop.
"""

from __future__ import annotations

import subprocess
from typing import Annotated

from langchain_core.tools import tool

from .logging_config import get_logger
from .settings import get_settings

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Kubernetes
# ---------------------------------------------------------------------------


@tool
def k8s_get_pod_status(
    service: Annotated[str, "Kubernetes app label / service name (e.g. 'payments')"],
    namespace: Annotated[str, "Kubernetes namespace (default: 'default')"] = "default",
) -> str:
    """Return the pod status summary for a service from Kubernetes."""
    settings = get_settings()
    if not settings.k8s_enabled:
        return (
            f"[k8s dry-run] k8s_enabled=false — would run: "
            f"kubectl get pods -n {namespace} -l app={service}"
        )
    try:
        out = subprocess.check_output(
            ["kubectl", "get", "pods", "-n", namespace, "-l", f"app={service}", "--no-headers"],
            timeout=15,
            stderr=subprocess.STDOUT,
        )
        return out.decode().strip() or f"No pods found for app={service} in {namespace}."
    except subprocess.CalledProcessError as exc:
        logger.warning("k8s_tool_error", error=exc.output.decode())
        return f"[k8s error] {exc.output.decode()}"
    except Exception as exc:
        logger.warning("k8s_tool_error", error=str(exc))
        return f"[k8s error] {exc}"


# ---------------------------------------------------------------------------
# Datadog
# ---------------------------------------------------------------------------


@tool
def datadog_get_metric_snapshot(
    service: Annotated[str, "Service name to query Datadog metrics for"],
    window_minutes: Annotated[int, "Time window in minutes (default: 60)"] = 60,
) -> str:
    """Fetch a CPU / error-rate metric snapshot for a service from Datadog."""
    import time

    import httpx

    settings = get_settings()
    if not settings.datadog_api_key:
        return (
            f"[datadog dry-run] No API key configured — would query {window_minutes}m "
            f"snapshot for service={service}."
        )
    now = int(time.time())
    query = f"avg:system.cpu.user{{service:{service}}}"
    url = f"https://api.{settings.datadog_site}/api/v1/query"
    try:
        resp = httpx.get(
            url,
            headers={
                "DD-API-KEY": settings.datadog_api_key,
                "DD-APPLICATION-KEY": settings.datadog_app_key or "",
            },
            params={"query": query, "from": now - window_minutes * 60, "to": now},
            timeout=15,
        )
        resp.raise_for_status()
        series = resp.json().get("series", [])
        if not series:
            return f"No metric data for service={service} in the last {window_minutes}m."
        pts = [p[1] for p in series[0].get("pointlist", []) if p[1] is not None]
        avg = sum(pts) / len(pts) if pts else 0
        return f"CPU avg {window_minutes}m: {avg:.2f}% — service={service}."
    except Exception as exc:
        logger.warning("datadog_tool_error", error=str(exc))
        return f"[datadog error] {exc}"


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


@tool
def slack_post_incident_summary(
    channel: Annotated[str, "Slack channel to post to (e.g. '#incidents')"],
    message: Annotated[str, "Message text to post"],
) -> str:
    """Post an incident summary message to a Slack channel via incoming webhook."""
    import httpx

    settings = get_settings()
    if not settings.slack_webhook_url:
        return (
            f"[slack dry-run] No webhook URL configured — would post to {channel}: "
            f"{message[:80]}..."
        )
    try:
        resp = httpx.post(
            settings.slack_webhook_url,
            json={"channel": channel, "text": message},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("slack_message_posted", channel=channel)
        return f"Message posted to {channel} successfully."
    except Exception as exc:
        logger.warning("slack_tool_error", error=str(exc))
        return f"[slack error] {exc}"


# ---------------------------------------------------------------------------
# Jira
# ---------------------------------------------------------------------------


@tool
def jira_create_incident_ticket(
    summary: Annotated[str, "Ticket summary / title"],
    description: Annotated[str, "Ticket description (timeline, impact, next steps)"],
) -> str:
    """Create a Jira post-incident task in the configured project."""
    import httpx

    settings = get_settings()
    if not (settings.jira_url and settings.jira_api_token and settings.jira_project_key):
        return f"[jira dry-run] Jira not configured — would create ticket: {summary!r}."
    url = f"{settings.jira_url.rstrip('/')}/rest/api/3/issue"
    try:
        resp = httpx.post(
            url,
            auth=(settings.jira_email or "", settings.jira_api_token),
            json={
                "fields": {
                    "project": {"key": settings.jira_project_key},
                    "summary": summary,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": description}],
                            }
                        ],
                    },
                    "issuetype": {"name": "Task"},
                }
            },
            timeout=15,
        )
        resp.raise_for_status()
        key = resp.json().get("key", "UNKNOWN")
        ticket_url = f"{settings.jira_url.rstrip('/')}/browse/{key}"
        logger.info("jira_ticket_created", key=key, url=ticket_url)
        return f"Jira ticket created: {ticket_url}"
    except Exception as exc:
        logger.warning("jira_tool_error", error=str(exc))
        return f"[jira error] {exc}"


# ---------------------------------------------------------------------------
# Registry — used by ToolNode and for direct invocation in graph nodes
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    k8s_get_pod_status,
    datadog_get_metric_snapshot,
    slack_post_incident_summary,
    jira_create_incident_ticket,
]
