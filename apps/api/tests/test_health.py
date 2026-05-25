"""Tests for GET /api/health."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_health_schema(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert "status" in body
    assert "service" in body
    assert "checks" in body
    assert body["service"] == "aegisops-api"


def test_health_postgres_ok(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["checks"].get("postgres") == "ok", (
        f"postgres check failed: {body['checks'].get('postgres')}"
    )


def test_health_redis_ok(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["checks"].get("redis") == "ok", f"redis check failed: {body['checks'].get('redis')}"


def test_health_overall_ok(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok", f"overall status is not ok: {body}"
