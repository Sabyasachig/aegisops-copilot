"""Tests for GET /api/incidents and GET /api/incidents/{id}."""
from __future__ import annotations

from fastapi.testclient import TestClient

# IDs that are seeded by store.py on startup
SEED_IDS = {"INC-2048", "INC-2081", "INC-2093"}


def test_list_incidents_returns_200(client: TestClient) -> None:
    resp = client.get("/api/incidents")
    assert resp.status_code == 200


def test_list_incidents_contains_seeded_data(client: TestClient) -> None:
    body = client.get("/api/incidents").json()
    assert "incidents" in body
    assert isinstance(body["incidents"], list)
    ids = {inc["id"] for inc in body["incidents"]}
    assert SEED_IDS.issubset(ids), f"Missing seed incidents. Got: {ids}"


def test_list_incidents_has_source_field(client: TestClient) -> None:
    body = client.get("/api/incidents").json()
    assert body.get("source") in ("db", "cache")


def test_list_incidents_second_call_from_cache(client: TestClient) -> None:
    client.get("/api/incidents")  # warm the cache
    body = client.get("/api/incidents").json()
    assert body.get("source") == "cache"


def test_get_incident_returns_200(client: TestClient) -> None:
    resp = client.get("/api/incidents/INC-2048")
    assert resp.status_code == 200


def test_get_incident_schema(client: TestClient) -> None:
    body = client.get("/api/incidents/INC-2048").json()
    inc = body["incident"]
    for field in ("id", "title", "service", "severity", "status", "owner"):
        assert field in inc, f"Missing field: {field}"


def test_get_incident_correct_id(client: TestClient) -> None:
    body = client.get("/api/incidents/INC-2048").json()
    assert body["incident"]["id"] == "INC-2048"


def test_get_incident_not_found(client: TestClient) -> None:
    resp = client.get("/api/incidents/INC-DOES-NOT-EXIST")
    assert resp.status_code == 404


def test_get_incident_all_seed_ids_exist(client: TestClient) -> None:
    for inc_id in SEED_IDS:
        resp = client.get(f"/api/incidents/{inc_id}")
        assert resp.status_code == 200, f"Seed incident {inc_id} not found"
