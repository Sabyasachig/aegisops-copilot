from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_operator
from ..db.engine import get_db
from ..db.repository import create_agent_run, get_incident
from ..limiter import get_user_identifier, limiter
from ..logging_config import bind_log_context, get_logger
from ..models import EnqueueResponse
from ..settings import get_settings
from ..tasks import execute_incident_task

logger = get_logger(__name__)

router = APIRouter(tags=["execution"])


# ---------------------------------------------------------------------------
# Rate-limit helpers — zero-argument callables so the limit string is resolved
# at request time and therefore configurable via env vars at runtime.
# ---------------------------------------------------------------------------


def _ip_limit() -> str:
    return get_settings().rate_limit_execute_ip


def _user_limit() -> str:
    return get_settings().rate_limit_execute_user


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
@limiter.limit(_user_limit, key_func=get_user_identifier)
@limiter.limit(_ip_limit)
async def execute_incident(
    request: Request,
    incident_id: str,
    response: Response,
    current_user: str = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> EnqueueResponse:
    bind_log_context(user_id=current_user, incident_id=incident_id)

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
        user_id=current_user,
        provider=settings.llm_provider,
        model_name=settings.llm_model,
    )

    logger.info(
        "incident_execution_enqueued",
        task_id=task.id,
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
