"""Slack notifications on agent run lifecycle events.

Sends Slack messages (via incoming webhook) when an agent run:
  * completes (``done`` / ``blocked`` / ``rejected``)
  * requires human approval (``needs_human``)

The needs-human message includes Approve/Reject deep-links back to the
AegisOps dashboard so an on-call responder can act from Slack.

Design notes
------------
* This module is a pure notification sink. Failures are logged and swallowed
  — a Slack outage must never break the incident workflow.
* Notifications are opt-in via ``AIOPS_SLACK_NOTIFICATIONS_ENABLED``. When
  disabled, all ``notify_*`` calls become no-ops.
* When ``AIOPS_SLACK_WEBHOOK_URL`` is unset, the module runs in dry-run mode
  and only logs the intended payload.
* This is distinct from the ``slack_post_incident_summary`` LangGraph tool in
  ``tools.py``: that tool is invoked by the LLM agent as part of its
  reasoning; this module is a system-level lifecycle hook driven by the task
  runner.
"""

from __future__ import annotations

from typing import Any

import httpx

from .logging_config import get_logger
from .settings import get_settings

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Severity → emoji / color mapping (Slack Block Kit `attachments[].color`
# expects a hex string or the shortcuts "good" / "warning" / "danger").
# ---------------------------------------------------------------------------

_SEVERITY_EMOJI: dict[str, str] = {
    "critical": ":rotating_light:",
    "high": ":red_circle:",
    "medium": ":large_orange_diamond:",
    "low": ":large_blue_circle:",
    "info": ":information_source:",
}

_STATUS_EMOJI: dict[str, str] = {
    "done": ":white_check_mark:",
    "blocked": ":no_entry:",
    "rejected": ":x:",
    "needs_human": ":hourglass_flowing_sand:",
}

_STATUS_COLOR: dict[str, str] = {
    "done": "good",
    "blocked": "warning",
    "rejected": "danger",
    "needs_human": "#f2c744",
}


def _severity_emoji(severity: str | None) -> str:
    return _SEVERITY_EMOJI.get((severity or "").lower(), ":grey_question:")


def _status_emoji(status: str) -> str:
    return _STATUS_EMOJI.get(status, ":grey_question:")


def _status_color(status: str) -> str:
    return _STATUS_COLOR.get(status, "#cccccc")


def _incident_url(incident_id: str) -> str:
    """Build a link to the incident detail page on the AegisOps dashboard."""
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/incidents/{incident_id}"


def _build_completion_blocks(
    *,
    incident_id: str,
    incident_title: str,
    severity: str | None,
    service: str | None,
    run_id: str,
    status: str,
    summary: str,
    next_action: str | None,
) -> list[dict[str, Any]]:
    """Build Slack Block Kit blocks for a completed run."""
    sev_line = f"{_severity_emoji(severity)} *{(severity or 'unknown').title()}*"
    if service:
        sev_line += f"  ·  service `{service}`"

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{_status_emoji(status)} Run {status.replace('_', ' ')}: "
                        f"{incident_title[:120]}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Severity*\n{sev_line}"},
                {"type": "mrkdwn", "text": f"*Run*\n`{run_id}`"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary*\n{summary[:2000]}"},
        },
    ]
    if next_action:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Next action*\n{next_action[:1000]}"},
            }
        )
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open incident", "emoji": True},
                    "url": _incident_url(incident_id),
                    "style": "primary",
                }
            ],
        }
    )
    return blocks


def _build_needs_human_blocks(
    *,
    incident_id: str,
    incident_title: str,
    severity: str | None,
    service: str | None,
    run_id: str,
    proposed_action: str | None,
) -> list[dict[str, Any]]:
    """Build Slack Block Kit blocks for a run awaiting human approval."""
    sev_line = f"{_severity_emoji(severity)} *{(severity or 'unknown').title()}*"
    if service:
        sev_line += f"  ·  service `{service}`"

    base = get_settings().public_base_url.rstrip("/")
    approve_url = f"{base}/incidents/{incident_id}?run={run_id}&decision=approve"
    reject_url = f"{base}/incidents/{incident_id}?run={run_id}&decision=reject"

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{_status_emoji('needs_human')} Approval needed: "
                        f"{incident_title[:120]}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Severity*\n{sev_line}"},
                {"type": "mrkdwn", "text": f"*Run*\n`{run_id}`"},
            ],
        },
    ]
    if proposed_action:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Proposed action*\n{proposed_action[:1500]}",
                },
            }
        )
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve", "emoji": True},
                    "url": approve_url,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject", "emoji": True},
                    "url": reject_url,
                    "style": "danger",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open incident", "emoji": True},
                    "url": _incident_url(incident_id),
                },
            ],
        }
    )
    return blocks


async def _post_to_slack(payload: dict[str, Any]) -> str:
    """POST a Block Kit payload to the configured incoming webhook.

    Returns a short status string. Never raises: any failure is logged and
    reported as an ``[slack error] …`` string so the caller can keep going.
    """
    settings = get_settings()
    if not settings.slack_notifications_enabled:
        logger.debug("slack_notifications_disabled")
        return "[slack disabled]"
    if not settings.slack_webhook_url:
        logger.info("slack_notification_dry_run", text=payload.get("text"))
        return "[slack dry-run]"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(settings.slack_webhook_url, json=payload)
            resp.raise_for_status()
        logger.info("slack_notification_sent", text=payload.get("text"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 – never break the workflow
        logger.warning("slack_notification_failed", error=str(exc))
        return f"[slack error] {exc}"


async def notify_run_completed(
    *,
    incident_id: str,
    incident_title: str,
    severity: str | None,
    service: str | None,
    run_id: str,
    status: str,
    summary: str,
    next_action: str | None = None,
) -> str:
    """Send a Slack notification when a run finishes (done/blocked/rejected)."""
    if status not in {"done", "blocked", "rejected"}:
        return "[slack skipped]"
    settings = get_settings()
    fallback_text = (
        f"{_status_emoji(status)} Run {status} — {incident_title} "
        f"(severity: {severity or 'unknown'})"
    )
    payload = {
        "channel": settings.slack_default_channel,
        "text": fallback_text,
        "attachments": [
            {
                "color": _status_color(status),
                "blocks": _build_completion_blocks(
                    incident_id=incident_id,
                    incident_title=incident_title,
                    severity=severity,
                    service=service,
                    run_id=run_id,
                    status=status,
                    summary=summary,
                    next_action=next_action,
                ),
            }
        ],
    }
    return await _post_to_slack(payload)


async def notify_run_needs_human(
    *,
    incident_id: str,
    incident_title: str,
    severity: str | None,
    service: str | None,
    run_id: str,
    proposed_action: str | None = None,
) -> str:
    """Send a Slack notification when a run enters ``needs_human`` state."""
    settings = get_settings()
    fallback_text = (
        f"{_status_emoji('needs_human')} Approval needed — {incident_title} "
        f"(severity: {severity or 'unknown'})"
    )
    payload = {
        "channel": settings.slack_default_channel,
        "text": fallback_text,
        "attachments": [
            {
                "color": _status_color("needs_human"),
                "blocks": _build_needs_human_blocks(
                    incident_id=incident_id,
                    incident_title=incident_title,
                    severity=severity,
                    service=service,
                    run_id=run_id,
                    proposed_action=proposed_action,
                ),
            }
        ],
    }
    return await _post_to_slack(payload)


__all__ = [
    "notify_run_completed",
    "notify_run_needs_human",
]
