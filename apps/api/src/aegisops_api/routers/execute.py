from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_db
from ..db.repository import create_agent_run, get_incident
from ..models import EnqueueResponse
from ..settings import get_settings
from ..tasks import execute_incident_task

router = APIRouter(tags=["execution"])


@router.post(
    "/incidents/{incident_id}/execute",
    response_model=EnqueueResponse,
    status_code=202,
    summary="Enqueue an incident workflow run",
    description=(
        "Immediately returns a `task_id`. "
        "Poll `GET /api/tasks/{task_id}` to check progress and retrieve the result."
    ),
)
async def execute_incident(
    incident_id: str, db: AsyncSession = Depends(get_db)
) -> EnqueueResponse:
    incident = await get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    settings = get_settings()

    # Persist a "queued" run record so the audit trail is complete from the start
    queued_run = await create_agent_run(
        db,
        incident_id=incident.id,
        agent_name="incident-ops",
        summary=f"Queued LangGraph workflow for {incident.title}",
    )

    # Dispatch to Celery — this is non-blocking
    task = execute_incident_task.delay(
        incident_id=incident.id,
        run_id=queued_run.id,
        provider=settings.llm_provider,
        model_name=settings.llm_model,
    )

    return EnqueueResponse(
        task_id=task.id,
        run_id=queued_run.id,
        incident_id=incident.id,
        poll_url=f"/api/tasks/{task.id}",
    )

