"""Tests for Prometheus metrics exposure."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_metrics_endpoint_returns_200(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_endpoint_has_prometheus_content_type(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert "text/plain" in resp.headers.get("content-type", "")


def test_metrics_contains_custom_metric_names(client: TestClient) -> None:
    text = client.get("/metrics").text
    assert "agent_run_duration_seconds" in text
    assert "llm_token_total" in text
    assert "incident_mttr_seconds" in text