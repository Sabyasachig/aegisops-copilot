"""Pytest configuration and shared fixtures.

Sets env vars BEFORE any aegisops_api imports so that pydantic-settings
reads the test values (lru_cache on get_settings() is reset below).
"""

from __future__ import annotations

import os

# ── Override settings for the test process ───────────────────────────────────
# CI sets these via the `env:` block in ci.yml; local dev can override too.
os.environ.setdefault(
    "AIOPS_DATABASE_URL",
    "postgresql+asyncpg://aegisops:aegisops@localhost:5432/aegisops_test",
)
os.environ.setdefault("AIOPS_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("AIOPS_CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("AIOPS_CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("AIOPS_LANGSMITH_TRACING", "false")
os.environ.setdefault("AIOPS_INITIAL_ADMIN_PASSWORD", "testpass123")
os.environ.setdefault("AIOPS_WEBHOOK_SECRET", "test-webhook-secret-aegisops-hmac")
# Use NullPool so asyncpg doesn't bind to the wrong event loop under anyio
os.environ["AIOPS_TESTING"] = "true"

# ── Imports that depend on the env vars above ─────────────────────────────────
import pytest
from fastapi.testclient import TestClient

from aegisops_api.settings import get_settings


@pytest.fixture(scope="session", autouse=True)
def _clear_settings_cache():
    """Ensure the lru_cached Settings instance reflects the overridden env vars."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def client():
    """Synchronous TestClient wrapping the full FastAPI app (lifespan included).

    Uses a *module* scope so that DB tables are created once per test module and
    the seed incidents are present for all tests in that module.
    """
    from aegisops_api.main import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc


@pytest.fixture(scope="module")
def authed_client(client: TestClient) -> TestClient:
    """TestClient pre-configured with a valid Bearer token for the seeded admin user."""
    resp = client.post(
        "/api/auth/token",
        json={"username": "admin", "password": "testpass123"},
    )
    assert resp.status_code == 200, f"Failed to obtain test token: {resp.text}"
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
