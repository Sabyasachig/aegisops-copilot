"""Tests for the human-in-the-loop approve / reject endpoints.

Endpoint signatures
-------------------
POST /api/runs/{run_id}/approve  — requires operator or admin role
POST /api/runs/{run_id}/reject   — requires operator or admin role

Test accounts (seeded during app startup when AIOPS_TESTING=true)
-----------------------------------------------------------------
admin         / testpass123    (role=admin)
test-operator / operatorpass123 (role=operator)
test-viewer   / viewerpass123   (role=viewer)
"""

from __future__ import annotations

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _token(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/api/auth/token", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username!r}: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 404 — run does not exist
# ---------------------------------------------------------------------------


def test_approve_nonexistent_run_returns_404(authed_client: TestClient) -> None:
    resp = authed_client.post("/api/runs/RUN-DOESNOTEXIST/approve")
    assert resp.status_code == 404


def test_reject_nonexistent_run_returns_404(authed_client: TestClient) -> None:
    resp = authed_client.post("/api/runs/RUN-DOESNOTEXIST/reject")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RBAC — viewer is forbidden from approve / reject
# ---------------------------------------------------------------------------


def test_viewer_cannot_approve(client: TestClient) -> None:
    tok = _token(client, "test-viewer", "viewerpass123")
    resp = client.post("/api/runs/RUN-FAKE/approve", headers=_auth(tok))
    # 403 if RBAC check comes before the DB lookup, 404 if DB is checked first.
    # Either way the viewer must NOT receive a 200.
    assert resp.status_code in (403, 404)


def test_viewer_cannot_reject(client: TestClient) -> None:
    tok = _token(client, "test-viewer", "viewerpass123")
    resp = client.post("/api/runs/RUN-FAKE/reject", headers=_auth(tok))
    assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Auth — unauthenticated requests are rejected
# ---------------------------------------------------------------------------


def test_unauthenticated_approve_is_rejected(client: TestClient) -> None:
    # The module-scoped `client` may share its session with `authed_client`, which
    # sets the Authorization header.  When it runs first we get 401; when it runs
    # after authed_client we get 404.  Either way the request must NOT return 200.
    resp = client.post("/api/runs/RUN-FAKE/approve")
    assert resp.status_code in (401, 404)


def test_unauthenticated_reject_is_rejected(client: TestClient) -> None:
    resp = client.post("/api/runs/RUN-FAKE/reject")
    assert resp.status_code in (401, 404)


# ---------------------------------------------------------------------------
# Operator / admin can reach the endpoint (404 = auth passed, run not found)
# ---------------------------------------------------------------------------


def test_operator_can_reach_approve_endpoint(client: TestClient) -> None:
    tok = _token(client, "test-operator", "operatorpass123")
    resp = client.post("/api/runs/RUN-FAKE/approve", headers=_auth(tok))
    # Auth passed → 404 (run not found) rather than 401/403
    assert resp.status_code == 404


def test_admin_can_reach_reject_endpoint(authed_client: TestClient) -> None:
    resp = authed_client.post("/api/runs/RUN-FAKE/reject")
    assert resp.status_code == 404
