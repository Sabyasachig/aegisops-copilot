"""Tests for POST /api/webhooks/generic and POST /api/webhooks/pagerduty.

Covers:
- Valid HMAC signature → 201
- Missing signature → 403
- Invalid signature → 403
- HMAC helper unit tests
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from fastapi.testclient import TestClient

from aegisops_api.routers.webhooks import (
    _compute_hmac_sha256,
    _verify_generic_signature,
    _verify_pagerduty_signature,
)

_SECRET = "test-webhook-secret-aegisops-hmac"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    """Return a short unique hex string for use in incident IDs."""
    return uuid.uuid4().hex[:8].upper()


def _sign_generic(body: bytes, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _sign_pagerduty(body: bytes, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"v1={digest}"


# ---------------------------------------------------------------------------
# Unit tests for HMAC helpers
# ---------------------------------------------------------------------------


class TestComputeHmac:
    def test_deterministic(self) -> None:
        a = _compute_hmac_sha256("secret", b"body")
        b = _compute_hmac_sha256("secret", b"body")
        assert a == b

    def test_different_secrets_differ(self) -> None:
        a = _compute_hmac_sha256("secret1", b"body")
        b = _compute_hmac_sha256("secret2", b"body")
        assert a != b

    def test_different_bodies_differ(self) -> None:
        a = _compute_hmac_sha256("secret", b"body1")
        b = _compute_hmac_sha256("secret", b"body2")
        assert a != b


class TestVerifyGenericSignature:
    def test_valid_sha256_prefix(self) -> None:
        body = b'{"id":"INC-001"}'
        header = _sign_generic(body)
        assert _verify_generic_signature(body, header, _SECRET) is True

    def test_valid_without_prefix(self) -> None:
        body = b'{"id":"INC-001"}'
        digest = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_generic_signature(body, digest, _SECRET) is True

    def test_wrong_secret(self) -> None:
        body = b'{"id":"INC-001"}'
        header = _sign_generic(body, secret="wrong-secret")
        assert _verify_generic_signature(body, header, _SECRET) is False

    def test_tampered_body(self) -> None:
        body = b'{"id":"INC-001"}'
        header = _sign_generic(body)
        assert _verify_generic_signature(b'{"id":"INC-TAMPERED"}', header, _SECRET) is False


class TestVerifyPagerDutySignature:
    def test_valid_v1_prefix(self) -> None:
        body = b'{"event":{}}'
        header = _sign_pagerduty(body)
        assert _verify_pagerduty_signature(body, header, _SECRET) is True

    def test_multiple_signatures_one_valid(self) -> None:
        body = b'{"event":{}}'
        valid = _sign_pagerduty(body)
        header = f"v1=deadbeef,{valid}"
        assert _verify_pagerduty_signature(body, header, _SECRET) is True

    def test_all_invalid(self) -> None:
        body = b'{"event":{}}'
        header = "v1=deadbeef,v1=cafebabe"
        assert _verify_pagerduty_signature(body, header, _SECRET) is False

    def test_wrong_prefix_ignored(self) -> None:
        body = b'{"event":{}}'
        digest = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
        # Correct digest but wrong prefix
        header = f"v2={digest}"
        assert _verify_pagerduty_signature(body, header, _SECRET) is False


# ---------------------------------------------------------------------------
# Integration tests — /api/webhooks/generic
# ---------------------------------------------------------------------------


def test_generic_valid_signature_returns_201(client: TestClient) -> None:
    payload = {"id": f"INC-{_uid()}", "title": "Test HMAC incident", "service": "test-svc"}
    body = json.dumps(payload).encode()
    resp = client.post(
        "/api/webhooks/generic",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": _sign_generic(body),
        },
    )
    assert resp.status_code == 201


def test_generic_missing_signature_returns_403(client: TestClient) -> None:
    payload = {"id": f"INC-{_uid()}", "title": "Test HMAC incident", "service": "test-svc"}
    body = json.dumps(payload).encode()
    resp = client.post(
        "/api/webhooks/generic",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 403


def test_generic_invalid_signature_returns_403(client: TestClient) -> None:
    payload = {"id": f"INC-{_uid()}", "title": "Test HMAC incident", "service": "test-svc"}
    body = json.dumps(payload).encode()
    resp = client.post(
        "/api/webhooks/generic",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": "sha256=deadbeefdeadbeefdeadbeefdeadbeef",
        },
    )
    assert resp.status_code == 403


def test_generic_tampered_body_returns_403(client: TestClient) -> None:
    inc_id = f"INC-{_uid()}"
    original = json.dumps({"id": inc_id, "title": "HMAC test", "service": "svc"}).encode()
    sig = _sign_generic(original)
    tampered = original.replace(inc_id.encode(), b"INC-TAMPERED")
    resp = client.post(
        "/api/webhooks/generic",
        content=tampered,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": sig},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Integration tests — /api/webhooks/pagerduty
# ---------------------------------------------------------------------------


def _pd_payload(inc_id: str) -> dict:
    return {
        "event": {
            "event_type": "incident.triggered",
            "data": {
                "id": inc_id,
                "title": "PD HMAC test",
                "severity": "critical",
                "service": {"name": "api"},
                "assignees": [{"summary": "oncall-team"}],
                "body": {"details": "Something broke"},
            },
        }
    }


def test_pagerduty_valid_signature_returns_201(client: TestClient) -> None:
    body = json.dumps(_pd_payload(_uid())).encode()
    resp = client.post(
        "/api/webhooks/pagerduty",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PagerDuty-Signature": _sign_pagerduty(body),
        },
    )
    assert resp.status_code == 201


def test_pagerduty_missing_signature_returns_403(client: TestClient) -> None:
    body = json.dumps(_pd_payload(_uid())).encode()
    resp = client.post(
        "/api/webhooks/pagerduty",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 403


def test_pagerduty_invalid_signature_returns_403(client: TestClient) -> None:
    body = json.dumps(_pd_payload(_uid())).encode()
    resp = client.post(
        "/api/webhooks/pagerduty",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PagerDuty-Signature": "v1=deadbeefdeadbeefdeadbeef",
        },
    )
    assert resp.status_code == 403


def test_pagerduty_multi_signature_one_valid(client: TestClient) -> None:
    """PagerDuty may send multiple v1= tokens; any valid one should pass."""
    body = json.dumps(_pd_payload(_uid())).encode()
    valid = _sign_pagerduty(body)
    header = f"v1=deadbeef,{valid}"
    resp = client.post(
        "/api/webhooks/pagerduty",
        content=body,
        headers={"Content-Type": "application/json", "X-PagerDuty-Signature": header},
    )
    assert resp.status_code == 201


def test_pagerduty_non_trigger_event_returns_ignored(client: TestClient) -> None:
    payload = {"event": {"event_type": "incident.resolved", "data": {}}}
    body = json.dumps(payload).encode()
    resp = client.post(
        "/api/webhooks/pagerduty",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-PagerDuty-Signature": _sign_pagerduty(body),
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "ignored"
