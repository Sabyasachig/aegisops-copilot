"""Tests for Issue #18: Slack lifecycle notifications.

Covers the pure notification module in ``aegisops_api.notifications``:

* dry-run behaviour when the webhook URL is unset
* disabled-mode no-op when the feature flag is off
* successful POST when both are configured
* graceful failure when Slack returns an error
* Block Kit payload shape (severity emoji, run status header, deep-links,
  Approve/Reject buttons on needs_human)
* completion notification is skipped for non-terminal statuses
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aegisops_api import notifications
from aegisops_api.settings import get_settings


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run a coroutine on a fresh event loop (repo pattern)."""
    return asyncio.run(coro)


class _FakeSettings:
    """Duck-typed stand-in for ``Settings`` used inside the module."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        webhook: str | None = "https://hooks.slack.example/T000/B000/XXX",
        channel: str = "#incidents",
        base_url: str = "https://aegisops.example.com",
    ) -> None:
        self.slack_notifications_enabled = enabled
        self.slack_webhook_url = webhook
        self.slack_default_channel = channel
        self.public_base_url = base_url


# ---------------------------------------------------------------------------
# Feature-flag / dry-run behaviour
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    def test_disabled_flag_returns_disabled_marker(self) -> None:
        with patch.object(
            notifications,
            "get_settings",
            return_value=_FakeSettings(enabled=False),
        ):
            result = _run(
                notifications.notify_run_completed(
                    incident_id="INC-1",
                    incident_title="db down",
                    severity="critical",
                    service="payments",
                    run_id="RUN-1",
                    status="done",
                    summary="fixed",
                )
            )
        assert result == "[slack disabled]"

    def test_missing_webhook_returns_dry_run_marker(self) -> None:
        with patch.object(
            notifications,
            "get_settings",
            return_value=_FakeSettings(webhook=None),
        ):
            result = _run(
                notifications.notify_run_completed(
                    incident_id="INC-1",
                    incident_title="db down",
                    severity="critical",
                    service="payments",
                    run_id="RUN-1",
                    status="done",
                    summary="fixed",
                )
            )
        assert result == "[slack dry-run]"

    def test_non_terminal_status_is_skipped(self) -> None:
        with patch.object(notifications, "get_settings", return_value=_FakeSettings()):
            result = _run(
                notifications.notify_run_completed(
                    incident_id="INC-1",
                    incident_title="db down",
                    severity="critical",
                    service="payments",
                    run_id="RUN-1",
                    status="running",  # not a terminal state
                    summary="in progress",
                )
            )
        assert result == "[slack skipped]"


# ---------------------------------------------------------------------------
# Successful POST + payload shape
# ---------------------------------------------------------------------------


def _capture_post() -> tuple[Any, dict[str, Any]]:
    """Return (patched_AsyncClient, holder) where holder captures the POST payload."""
    holder: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:  # pragma: no cover - trivial
            return None

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any]) -> _Resp:
            holder["url"] = url
            holder["json"] = json
            return _Resp()

    return _FakeClient, holder


class TestCompletionPayload:
    def test_done_status_posts_expected_block_kit(self) -> None:
        FakeClient, holder = _capture_post()
        with patch.object(notifications, "get_settings", return_value=_FakeSettings()), \
             patch.object(notifications.httpx, "AsyncClient", FakeClient):
            result = _run(
                notifications.notify_run_completed(
                    incident_id="INC-42",
                    incident_title="payments db saturated",
                    severity="critical",
                    service="payments-api",
                    run_id="RUN-abc",
                    status="done",
                    summary="Rolled back offending migration.",
                    next_action="Post-incident review at 3pm.",
                )
            )

        assert result == "ok"
        assert holder["url"] == "https://hooks.slack.example/T000/B000/XXX"

        payload = holder["json"]
        assert payload["channel"] == "#incidents"
        assert "Run done" in payload["text"]
        assert payload["text"].startswith(":white_check_mark:")

        attachment = payload["attachments"][0]
        assert attachment["color"] == "good"

        blocks = attachment["blocks"]
        header = blocks[0]
        assert header["type"] == "header"
        assert "Run done" in header["text"]["text"]
        assert "payments db saturated" in header["text"]["text"]

        summary_texts = [b for b in blocks if b["type"] == "section"]
        joined = " ".join(
            (b.get("text", {}) or {}).get("text", "")
            + " ".join(f.get("text", "") for f in b.get("fields", []))
            for b in summary_texts
        )
        assert "Rolled back offending migration." in joined
        assert "Post-incident review at 3pm." in joined
        assert "payments-api" in joined
        assert ":rotating_light:" in joined  # critical → siren emoji

        actions = [b for b in blocks if b["type"] == "actions"][0]
        urls = [e["url"] for e in actions["elements"]]
        assert any(u.endswith("/incidents/INC-42") for u in urls)

    def test_blocked_status_uses_warning_color(self) -> None:
        FakeClient, holder = _capture_post()
        with patch.object(notifications, "get_settings", return_value=_FakeSettings()), \
             patch.object(notifications.httpx, "AsyncClient", FakeClient):
            _run(
                notifications.notify_run_completed(
                    incident_id="INC-2",
                    incident_title="cache eviction storm",
                    severity="high",
                    service="cache",
                    run_id="RUN-2",
                    status="blocked",
                    summary="Waiting on infra team.",
                )
            )
        assert holder["json"]["attachments"][0]["color"] == "warning"

    def test_rejected_status_uses_danger_color(self) -> None:
        FakeClient, holder = _capture_post()
        with patch.object(notifications, "get_settings", return_value=_FakeSettings()), \
             patch.object(notifications.httpx, "AsyncClient", FakeClient):
            _run(
                notifications.notify_run_completed(
                    incident_id="INC-3",
                    incident_title="unauthorized deploy attempt",
                    severity="medium",
                    service="ci",
                    run_id="RUN-3",
                    status="rejected",
                    summary="Reviewer rejected the proposed rollback.",
                )
            )
        assert holder["json"]["attachments"][0]["color"] == "danger"

    def test_http_error_is_swallowed(self) -> None:
        class _BoomClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> "_BoomClient":
                return self

            async def __aexit__(self, *args: Any) -> None:
                return None

            async def post(self, url: str, json: dict[str, Any]) -> None:
                raise RuntimeError("slack down")

        with patch.object(notifications, "get_settings", return_value=_FakeSettings()), \
             patch.object(notifications.httpx, "AsyncClient", _BoomClient):
            result = _run(
                notifications.notify_run_completed(
                    incident_id="INC-1",
                    incident_title="t",
                    severity="low",
                    service="s",
                    run_id="R",
                    status="done",
                    summary="ok",
                )
            )
        assert result.startswith("[slack error]")


# ---------------------------------------------------------------------------
# needs_human notification with Approve/Reject deep-links
# ---------------------------------------------------------------------------


class TestNeedsHumanPayload:
    def test_needs_human_includes_approve_and_reject_buttons(self) -> None:
        FakeClient, holder = _capture_post()
        with patch.object(notifications, "get_settings", return_value=_FakeSettings()), \
             patch.object(notifications.httpx, "AsyncClient", FakeClient):
            result = _run(
                notifications.notify_run_needs_human(
                    incident_id="INC-77",
                    incident_title="restart production db",
                    severity="critical",
                    service="db-primary",
                    run_id="RUN-xyz",
                    proposed_action="Failover to replica and restart primary.",
                )
            )

        assert result == "ok"
        payload = holder["json"]
        assert payload["text"].startswith(":hourglass_flowing_sand:")

        attachment = payload["attachments"][0]
        assert attachment["color"] == "#f2c744"

        blocks = attachment["blocks"]
        actions = [b for b in blocks if b["type"] == "actions"][0]
        elements = actions["elements"]

        labels = [e["text"]["text"] for e in elements]
        assert "Approve" in labels
        assert "Reject" in labels
        assert "Open incident" in labels

        # Approve/Reject deep-links must include run + decision query params.
        approve = next(e for e in elements if e["text"]["text"] == "Approve")
        reject = next(e for e in elements if e["text"]["text"] == "Reject")
        assert approve["style"] == "primary"
        assert reject["style"] == "danger"
        assert "run=RUN-xyz" in approve["url"]
        assert "decision=approve" in approve["url"]
        assert "run=RUN-xyz" in reject["url"]
        assert "decision=reject" in reject["url"]
        assert approve["url"].startswith("https://aegisops.example.com/incidents/INC-77")

    def test_needs_human_disabled_flag_short_circuits(self) -> None:
        with patch.object(
            notifications,
            "get_settings",
            return_value=_FakeSettings(enabled=False),
        ):
            result = _run(
                notifications.notify_run_needs_human(
                    incident_id="INC-1",
                    incident_title="t",
                    severity="high",
                    service="s",
                    run_id="R",
                )
            )
        assert result == "[slack disabled]"


# ---------------------------------------------------------------------------
# Settings smoke-check: new fields exist with sane defaults
# ---------------------------------------------------------------------------


def test_settings_expose_new_fields() -> None:
    settings = get_settings()
    # Both fields exist and have safe defaults suitable for local dev.
    assert hasattr(settings, "slack_notifications_enabled")
    assert hasattr(settings, "public_base_url")
    assert settings.slack_notifications_enabled is False
    assert settings.public_base_url.startswith("http")


# ---------------------------------------------------------------------------
# Silence unused-import warnings for helpers used only inside test bodies.
# ---------------------------------------------------------------------------

_ = (AsyncMock, MagicMock, pytest)
