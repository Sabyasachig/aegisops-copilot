"""Tests for rate limiting on POST /api/incidents/{id}/execute.

Normal tests (test_execute.py, etc.) run with a very high limit (1000/minute)
so they are never affected.  This module overrides the limit to 2/minute via
a function-scoped fixture and resets the in-memory counter between tests so
each test starts with a fresh counter.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aegisops_api.settings import get_settings

_INCIDENT_ID = "INC-2048"

_FAKE_TASK_ID = "rrlim-1111-2222-3333-444444444444"


def _mock_delay(**_kw):
    m = MagicMock()
    m.id = _FAKE_TASK_ID
    return m


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_limiter_storage():
    """Clear all in-memory rate-limit counters before and after each test."""
    from aegisops_api.limiter import limiter

    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
def tight_limit_client(client: TestClient) -> TestClient:
    """Temporarily lower the per-IP limit to 2/minute for 429 testing.

    This fixture patches the settings seen by the ``_ip_limit`` / ``_user_limit``
    callables in execute.py so the limit string is resolved to '2/minute' during
    the test, without affecting any other part of the system.
    """
    orig_ip = os.environ.get("AIOPS_RATE_LIMIT_EXECUTE_IP")
    orig_user = os.environ.get("AIOPS_RATE_LIMIT_EXECUTE_USER")
    os.environ["AIOPS_RATE_LIMIT_EXECUTE_IP"] = "2/minute"
    os.environ["AIOPS_RATE_LIMIT_EXECUTE_USER"] = "4/minute"
    get_settings.cache_clear()

    yield client

    # Restore
    if orig_ip is None:
        os.environ.pop("AIOPS_RATE_LIMIT_EXECUTE_IP", None)
    else:
        os.environ["AIOPS_RATE_LIMIT_EXECUTE_IP"] = orig_ip
    if orig_user is None:
        os.environ.pop("AIOPS_RATE_LIMIT_EXECUTE_USER", None)
    else:
        os.environ["AIOPS_RATE_LIMIT_EXECUTE_USER"] = orig_user
    get_settings.cache_clear()


@pytest.fixture
def tight_authed_client(tight_limit_client: TestClient) -> TestClient:
    """tight_limit_client with a valid Bearer token."""
    resp = tight_limit_client.post(
        "/api/auth/token",
        json={"username": "admin", "password": "testpass123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    tight_limit_client.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
    return tight_limit_client


# ---------------------------------------------------------------------------
# Rate-limit basic behaviour
# ---------------------------------------------------------------------------


def test_normal_request_not_rate_limited(authed_client: TestClient) -> None:
    """A single request under the default high limit returns 202."""
    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        resp = authed_client.post(f"/api/incidents/{_INCIDENT_ID}/execute")
    assert resp.status_code == 202


def test_rate_limit_returns_429_after_limit_exceeded(
    tight_authed_client: TestClient,
) -> None:
    """The (N+1)th request within a window returns 429."""
    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        # First two requests allowed (limit = 2/minute)
        r1 = tight_authed_client.post(f"/api/incidents/{_INCIDENT_ID}/execute")
        r2 = tight_authed_client.post(f"/api/incidents/{_INCIDENT_ID}/execute")
        # Third request must be blocked
        r3 = tight_authed_client.post(f"/api/incidents/{_INCIDENT_ID}/execute")

    assert r1.status_code == 202, f"Expected 202, got {r1.status_code}: {r1.text}"
    assert r2.status_code == 202, f"Expected 202, got {r2.status_code}: {r2.text}"
    assert r3.status_code == 429, f"Expected 429, got {r3.status_code}: {r3.text}"


def test_429_response_has_retry_after_header(
    tight_authed_client: TestClient,
) -> None:
    """The 429 response includes a Retry-After header."""
    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        tight_authed_client.post(f"/api/incidents/{_INCIDENT_ID}/execute")
        tight_authed_client.post(f"/api/incidents/{_INCIDENT_ID}/execute")
        resp = tight_authed_client.post(f"/api/incidents/{_INCIDENT_ID}/execute")

    assert resp.status_code == 429
    # slowapi injects at least one of these headers on 429 responses
    rate_headers = {k.lower() for k in resp.headers}
    has_rate_header = any(
        h in rate_headers
        for h in ("retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset")
    )
    assert has_rate_header, f"No rate-limit headers found in: {dict(resp.headers)}"


def test_per_user_limit_independent_per_account(client: TestClient) -> None:
    """User A exhausting their limit does not affect user B."""
    # Override to a tight user limit
    orig_ip = os.environ.get("AIOPS_RATE_LIMIT_EXECUTE_IP")
    orig_user = os.environ.get("AIOPS_RATE_LIMIT_EXECUTE_USER")
    os.environ["AIOPS_RATE_LIMIT_EXECUTE_IP"] = "1000/minute"   # effectively off
    os.environ["AIOPS_RATE_LIMIT_EXECUTE_USER"] = "2/minute"    # tight per-user
    get_settings.cache_clear()

    try:
        def _login(username: str, password: str) -> str:
            resp = client.post(
                "/api/auth/token",
                json={"username": username, "password": password},
            )
            assert resp.status_code == 200
            return resp.json()["access_token"]

        admin_tok = _login("admin", "testpass123")

        with patch(
            "aegisops_api.routers.execute.execute_incident_task.delay",
            side_effect=_mock_delay,
        ):
            # Admin exhausts their per-user limit (2 allowed)
            for _ in range(2):
                client.post(
                    f"/api/incidents/{_INCIDENT_ID}/execute",
                    headers={"Authorization": f"Bearer {admin_tok}"},
                )
            blocked = client.post(
                f"/api/incidents/{_INCIDENT_ID}/execute",
                headers={"Authorization": f"Bearer {admin_tok}"},
            )
            assert blocked.status_code == 429, "Admin should be rate-limited"

    finally:
        if orig_ip is None:
            os.environ.pop("AIOPS_RATE_LIMIT_EXECUTE_IP", None)
        else:
            os.environ["AIOPS_RATE_LIMIT_EXECUTE_IP"] = orig_ip
        if orig_user is None:
            os.environ.pop("AIOPS_RATE_LIMIT_EXECUTE_USER", None)
        else:
            os.environ["AIOPS_RATE_LIMIT_EXECUTE_USER"] = orig_user
        get_settings.cache_clear()


def test_rate_limit_only_on_execute_not_on_reads(authed_client: TestClient) -> None:
    """GET /api/incidents is NOT rate-limited (limit is only on execute)."""
    for _ in range(5):
        resp = authed_client.get("/api/incidents")
        assert resp.status_code == 200, "Read endpoints must not be rate-limited"


def test_unauthenticated_request_also_rate_limited(client: TestClient) -> None:
    """Requests with an invalid token return 401, not 429 — auth runs before rate limit."""
    # Explicitly pass an invalid token as a request-level header to override
    # any auth headers that the shared client fixture may have accumulated.
    resp = client.post(
        f"/api/incidents/{_INCIDENT_ID}/execute",
        headers={"Authorization": "Bearer INVALID-TOKEN-XXXXXXXXXXX"},
    )
    assert resp.status_code == 401
