"""Task status polling endpoint.

``POST /api/incidents/{id}/execute`` now returns a ``task_id`` immediately.
Clients call ``GET /api/tasks/{task_id}`` to check progress.
"""

from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..models import ExecuteIncidentResponse, TaskStatusResponse
from ..worker import celery_app

router = APIRouter(tags=["tasks"], dependencies=[Depends(get_current_user)])


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Poll the status of an enqueued incident workflow run",
)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    result: AsyncResult = AsyncResult(task_id, app=celery_app)

    if result.state == "SUCCESS":
        data = result.result  # dict returned by execute_incident_task
        return TaskStatusResponse(
            task_id=task_id,
            state="SUCCESS",
            result=ExecuteIncidentResponse(
                incident_id=data["incident_id"],
                run_id=data["run_id"],
                status=data["status"],
                graph_run_id=data["graph_run_id"],
                summary=data["summary"],
                next_action=data["next_action"],
            ),
        )

    if result.state == "FAILURE":
        return TaskStatusResponse(
            task_id=task_id,
            state="FAILURE",
            error=str(result.result),  # result.result holds the exception on failure
        )

    # PENDING / STARTED / RETRY / REVOKED — no payload yet
    return TaskStatusResponse(task_id=task_id, state=result.state)  # type: ignore[arg-type]
