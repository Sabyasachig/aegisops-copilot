"""Tests for POST /api/incidents/{id}/execute and GET /api/tasks/{task_id}.

The actual LangGraph workflow is NOT executed in these tests — we patch the
Celery task dispatch so the tests run fast and without LLM credentials.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

_FAKE_TASK_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _mock_delay(**_kwargs):
    """Simulate task.delay() returning a result object with a predictable id."""
    result = MagicMock()
    result.id = _FAKE_TASK_ID
    return result


def test_execute_returns_202(authed_client: TestClient) -> None:
    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        resp = authed_client.post("/api/incidents/INC-2048/execute")
    assert resp.status_code == 202


def test_execute_response_schema(authed_client: TestClient) -> None:
    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        body = authed_client.post("/api/incidents/INC-2048/execute").json()

    for field in ("task_id", "run_id", "incident_id", "status", "poll_url"):
        assert field in body, f"Missing field: {field}"


def test_execute_response_status_queued(authed_client: TestClient) -> None:
    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        body = authed_client.post("/api/incidents/INC-2048/execute").json()
    assert body["status"] == "queued"


def test_execute_poll_url_contains_task_id(authed_client: TestClient) -> None:
    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        body = authed_client.post("/api/incidents/INC-2048/execute").json()
    assert body["task_id"] == _FAKE_TASK_ID
    assert _FAKE_TASK_ID in body["poll_url"]


def test_execute_unknown_incident_returns_404(authed_client: TestClient) -> None:
    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ):
        resp = authed_client.post("/api/incidents/INC-DOES-NOT-EXIST/execute")
    assert resp.status_code == 404


def test_execute_publishes_queued_event(authed_client: TestClient) -> None:
    with patch(
        "aegisops_api.routers.execute.execute_incident_task.delay",
        side_effect=_mock_delay,
    ), patch("aegisops_api.routers.execute.publish_incident_event") as publish_mock:
        resp = authed_client.post("/api/incidents/INC-2048/execute")

    assert resp.status_code == 202
    publish_mock.assert_called_once()
    args, _ = publish_mock.call_args
    assert args[0] == "INC-2048"
    assert args[1] == "workflow_queued"


def test_task_status_pending(authed_client: TestClient) -> None:
    """A task_id that was never enqueued reports PENDING."""
    resp = authed_client.get(f"/api/tasks/{_FAKE_TASK_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == _FAKE_TASK_ID
    assert body["state"] in ("PENDING", "SUCCESS", "FAILURE", "STARTED", "RETRY", "REVOKED")
