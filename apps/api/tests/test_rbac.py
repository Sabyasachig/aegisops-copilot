"""Tests for Role-Based Access Control (RBAC).

Three roles: viewer (read-only) · operator (can execute) · admin (full access).

Test accounts are seeded during app startup when AIOPS_TESTING=true:
  - test-viewer   / viewerpass123   (role=viewer)
  - test-operator / operatorpass123 (role=operator)
  - admin         / testpass123     (role=admin, from conftest)
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_SEED_INCIDENT_ID = "INC-2048"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _token(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/api/auth/token", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username!r}: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Viewer — read-only
# ---------------------------------------------------------------------------


def test_viewer_can_list_incidents(client: TestClient) -> None:
    tok = _token(client, "test-viewer", "viewerpass123")
    resp = client.get("/api/incidents", headers=_auth(tok))
    assert resp.status_code == 200


def test_viewer_can_get_incident(client: TestClient) -> None:
    tok = _token(client, "test-viewer", "viewerpass123")
    resp = client.get(f"/api/incidents/{_SEED_INCIDENT_ID}", headers=_auth(tok))
    assert resp.status_code == 200


def test_viewer_cannot_execute(client: TestClient) -> None:
    tok = _token(client, "test-viewer", "viewerpass123")
    resp = client.post(f"/api/incidents/{_SEED_INCIDENT_ID}/execute", headers=_auth(tok))
    assert resp.status_code == 403


def test_viewer_cannot_delete(client: TestClient) -> None:
    tok = _token(client, "test-viewer", "viewerpass123")
    resp = client.delete(f"/api/incidents/{_SEED_INCIDENT_ID}", headers=_auth(tok))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Operator — can execute, cannot delete
# ---------------------------------------------------------------------------


def test_operator_can_list_incidents(client: TestClient) -> None:
    tok = _token(client, "test-operator", "operatorpass123")
    resp = client.get("/api/incidents", headers=_auth(tok))
    assert resp.status_code == 200


def test_operator_can_execute(client: TestClient) -> None:
    from unittest.mock import MagicMock, patch

    tok = _token(client, "test-operator", "operatorpass123")

    def _mock_delay(**_kw):
        m = MagicMock()
        m.id = "bbbb-cccc"
        return m

    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        resp = client.post(
            f"/api/incidents/{_SEED_INCIDENT_ID}/execute",
            headers=_auth(tok),
        )
    assert resp.status_code == 202


def test_operator_cannot_delete(client: TestClient) -> None:
    tok = _token(client, "test-operator", "operatorpass123")
    resp = client.delete(f"/api/incidents/{_SEED_INCIDENT_ID}", headers=_auth(tok))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin — full access
# ---------------------------------------------------------------------------


def test_admin_can_list_incidents(client: TestClient) -> None:
    tok = _token(client, "admin", "testpass123")
    resp = client.get("/api/incidents", headers=_auth(tok))
    assert resp.status_code == 200


def test_admin_can_execute(client: TestClient) -> None:
    from unittest.mock import MagicMock, patch

    tok = _token(client, "admin", "testpass123")

    def _mock_delay(**_kw):
        m = MagicMock()
        m.id = "cccc-dddd"
        return m

    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        resp = client.post(
            f"/api/incidents/{_SEED_INCIDENT_ID}/execute",
            headers=_auth(tok),
        )
    assert resp.status_code == 202


def test_admin_can_delete_incident(client: TestClient) -> None:
    """Admin can delete — use a throwaway incident created first."""
    from unittest.mock import MagicMock, patch
    import json

    tok = _token(client, "admin", "testpass123")

    # First create an incident via the generic webhook (no auth needed)
    import hashlib, hmac
    secret = "test-webhook-secret-aegisops-hmac"
    payload = {"id": "INC-DELETE-ME", "title": "delete test", "service": "test"}
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    client.post(
        "/api/webhooks/generic",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": sig},
    )

    resp = client.delete("/api/incidents/INC-DELETE-ME", headers=_auth(tok))
    assert resp.status_code == 204


def test_admin_delete_nonexistent_returns_404(client: TestClient) -> None:
    tok = _token(client, "admin", "testpass123")
    resp = client.delete("/api/incidents/INC-DOES-NOT-EXIST", headers=_auth(tok))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------


def test_unauthed_cannot_delete(client: TestClient) -> None:
    resp = client.delete(f"/api/incidents/{_SEED_INCIDENT_ID}")
    assert resp.status_code == 401


def test_unauthed_cannot_execute(client: TestClient) -> None:
    resp = client.post(f"/api/incidents/{_SEED_INCIDENT_ID}/execute")
    assert resp.status_code == 401
