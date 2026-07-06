"""Tests for POST /api/auth/token and POST /api/auth/refresh."""

from __future__ import annotations

from fastapi.testclient import TestClient

_TEST_USERNAME = "admin"
_TEST_PASSWORD = "testpass123"


# ---------------------------------------------------------------------------
# POST /api/auth/token
# ---------------------------------------------------------------------------


def test_login_returns_200(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/token",
        json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD},
    )
    assert resp.status_code == 200


def test_login_response_schema(client: TestClient) -> None:
    body = client.post(
        "/api/auth/token",
        json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD},
    ).json()
    for field in ("access_token", "refresh_token", "token_type", "expires_in"):
        assert field in body, f"Missing field: {field}"


def test_login_token_type_is_bearer(client: TestClient) -> None:
    body = client.post(
        "/api/auth/token",
        json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD},
    ).json()
    assert body["token_type"] == "bearer"


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/token",
        json={"username": _TEST_USERNAME, "password": "wrong-password"},
    )
    assert resp.status_code == 401


def test_login_unknown_user_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/token",
        json={"username": "nobody", "password": "irrelevant"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/auth/refresh
# ---------------------------------------------------------------------------


def test_refresh_returns_200(client: TestClient) -> None:
    tokens = client.post(
        "/api/auth/token",
        json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD},
    ).json()
    resp = client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 200


def test_refresh_response_schema(client: TestClient) -> None:
    tokens = client.post(
        "/api/auth/token",
        json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD},
    ).json()
    body = client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    ).json()
    for field in ("access_token", "token_type", "expires_in"):
        assert field in body, f"Missing field: {field}"


def test_refresh_invalid_token_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "not.a.valid.token"},
    )
    assert resp.status_code == 401


def test_refresh_with_access_token_returns_401(client: TestClient) -> None:
    """Using an access token where a refresh token is required must fail."""
    tokens = client.post(
        "/api/auth/token",
        json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD},
    ).json()
    resp = client.post(
        "/api/auth/refresh",
        json={"refresh_token": tokens["access_token"]},  # wrong token type
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected routes — unauthenticated access
# ---------------------------------------------------------------------------


def test_incidents_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/incidents")
    assert resp.status_code == 401


def test_execute_without_token_returns_401(client: TestClient) -> None:
    resp = client.post("/api/incidents/INC-2048/execute")
    assert resp.status_code == 401


def test_providers_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/providers")
    assert resp.status_code == 401
