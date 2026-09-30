"""Tests for the extended webhook handlers (Issue #17).

Covers:
- POST /api/webhooks/opsgenie: HMAC verification, Create-action ingestion,
  priority-to-severity mapping, ignored non-Create actions.
- POST /api/webhooks/alertmanager: HMAC verification, firing ingestion,
  severity-label mapping, ignored resolved/empty payloads.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from fastapi.testclient import TestClient

from aegisops_api.routers.webhooks import (
    _map_alertmanager_severity,
    _map_opsgenie_priority,
)

_SECRET = "test-webhook-secret-aegisops-hmac"


def _uid() -> str:
    return uuid.uuid4().hex[:8].upper()


def _sign_generic(body: bytes, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ---------------------------------------------------------------------------
# Severity mapping — pure functions
# ---------------------------------------------------------------------------


class TestOpsGeniePriorityMapping:
    def test_p1_maps_to_critical(self) -> None:
        assert _map_opsgenie_priority("P1") == "critical"

    def test_p2_maps_to_high(self) -> None:
        assert _map_opsgenie_priority("P2") == "high"

    def test_p3_maps_to_medium(self) -> None:
        assert _map_opsgenie_priority("P3") == "medium"

    def test_p4_maps_to_low(self) -> None:
        assert _map_opsgenie_priority("P4") == "low"

    def test_p5_maps_to_info(self) -> None:
        assert _map_opsgenie_priority("P5") == "info"

    def test_lowercase_priority_is_normalized(self) -> None:
        assert _map_opsgenie_priority("p2") == "high"

    def test_missing_priority_defaults_to_high(self) -> None:
        assert _map_opsgenie_priority(None) == "high"

    def test_unknown_priority_defaults_to_high(self) -> None:
        assert _map_opsgenie_priority("P99") == "high"


class TestAlertmanagerSeverityMapping:
    def test_critical_label(self) -> None:
        assert _map_alertmanager_severity("critical") == "critical"

    def test_page_label_is_critical(self) -> None:
        assert _map_alertmanager_severity("page") == "critical"

    def test_warning_label_is_medium(self) -> None:
        assert _map_alertmanager_severity("warning") == "medium"

    def test_error_label_is_high(self) -> None:
        assert _map_alertmanager_severity("error") == "high"

    def test_info_label_is_info(self) -> None:
        assert _map_alertmanager_severity("info") == "info"

    def test_missing_label_defaults_to_medium(self) -> None:
        assert _map_alertmanager_severity(None) == "medium"

    def test_unknown_label_defaults_to_medium(self) -> None:
        assert _map_alertmanager_severity("mystery") == "medium"

    def test_uppercase_label_is_normalized(self) -> None:
        assert _map_alertmanager_severity("CRITICAL") == "critical"


# ---------------------------------------------------------------------------
# OpsGenie webhook integration tests
# ---------------------------------------------------------------------------


def _opsgenie_payload(alert_id: str, priority: str = "P2") -> dict:
    return {
        "action": "Create",
        "alert": {
            "alertId": alert_id,
            "message": "High CPU on api-01",
            "priority": priority,
            "tags": ["service:orders-api"],
            "owner": "sre-oncall",
            "description": "CPU at 92% for 5m",
        },
    }


def test_opsgenie_valid_signature_returns_201(client: TestClient) -> None:
    body = json.dumps(_opsgenie_payload(_uid())).encode()
    resp = client.post(
        "/api/webhooks/opsgenie",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": _sign_generic(body),
        },
    )
    assert resp.status_code == 201
    body_json = resp.json()
    assert body_json["status"] == "created"
    assert body_json["incident_id"].startswith("OG-")


def test_opsgenie_missing_signature_returns_403(client: TestClient) -> None:
    body = json.dumps(_opsgenie_payload(_uid())).encode()
    resp = client.post(
        "/api/webhooks/opsgenie",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 403


def test_opsgenie_invalid_signature_returns_403(client: TestClient) -> None:
    body = json.dumps(_opsgenie_payload(_uid())).encode()
    resp = client.post(
        "/api/webhooks/opsgenie",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": "sha256=deadbeefdeadbeefdeadbeef",
        },
    )
    assert resp.status_code == 403


def test_opsgenie_non_create_action_is_ignored(client: TestClient) -> None:
    payload = {"action": "Acknowledge", "alert": {"alertId": _uid()}}
    body = json.dumps(payload).encode()
    resp = client.post(
        "/api/webhooks/opsgenie",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": _sign_generic(body),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "ignored"


# ---------------------------------------------------------------------------
# Alertmanager webhook integration tests
# ---------------------------------------------------------------------------


def _alertmanager_payload(fingerprint: str, alert_status: str = "firing") -> dict:
    return {
        "version": "4",
        "status": alert_status,
        "alerts": [
            {
                "fingerprint": fingerprint,
                "labels": {
                    "alertname": "HighErrorRate",
                    "severity": "critical",
                    "service": "checkout-api",
                    "team": "revenue-eng",
                },
                "annotations": {
                    "summary": "5xx rate above SLO",
                    "description": "Error rate 12% over 5m",
                },
            }
        ],
        "commonLabels": {},
        "commonAnnotations": {},
    }


def test_alertmanager_valid_signature_returns_201(client: TestClient) -> None:
    body = json.dumps(_alertmanager_payload(_uid())).encode()
    resp = client.post(
        "/api/webhooks/alertmanager",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": _sign_generic(body),
        },
    )
    assert resp.status_code == 201
    body_json = resp.json()
    assert body_json["status"] == "created"
    assert body_json["incident_id"].startswith("AM-")


def test_alertmanager_missing_signature_returns_403(client: TestClient) -> None:
    body = json.dumps(_alertmanager_payload(_uid())).encode()
    resp = client.post(
        "/api/webhooks/alertmanager",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 403


def test_alertmanager_resolved_status_is_ignored(client: TestClient) -> None:
    body = json.dumps(_alertmanager_payload(_uid(), alert_status="resolved")).encode()
    resp = client.post(
        "/api/webhooks/alertmanager",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": _sign_generic(body),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "ignored"


def test_alertmanager_empty_alerts_is_ignored(client: TestClient) -> None:
    payload = {"version": "4", "status": "firing", "alerts": []}
    body = json.dumps(payload).encode()
    resp = client.post(
        "/api/webhooks/alertmanager",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": _sign_generic(body),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "ignored"
