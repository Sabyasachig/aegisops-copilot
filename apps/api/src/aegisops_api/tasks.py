"""Celery tasks for AegisOps Copilot.

All tasks run the LangGraph incident workflow as a background job so that the
HTTP endpoint can return a ``202 Accepted`` immediately with a ``task_id``.
Callers poll ``GET /api/tasks/{task_id}`` to check progress.
"""

from __future__ import annotations

import asyncio

from .logging_config import bind_log_context, clear_log_context, get_logger
from .worker import celery_app

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="aegisops.execute_incident",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=60,
)
def execute_incident_task(
    self,  # noqa: ANN001 – Celery bound task
    incident_id: str,
    run_id: str,
    user_id: str | None,
    provider: str,
    model_name: str,
) -> dict:
    """Run the LangGraph incident workflow and persist the result.

    Returns a dict that is stored in the Celery result backend and surfaced
    by ``GET /api/tasks/{task_id}``.
    """
    return asyncio.run(
        _execute_async(
            incident_id=incident_id,
            run_id=run_id,
            user_id=user_id,
            provider=provider,
            model_name=model_name,
        )
    )


async def _execute_async(
    incident_id: str,
    run_id: str,
    user_id: str | None,
    provider: str,
    model_name: str,
) -> dict:
    """Async implementation — called from the Celery task via asyncio.run()."""
    # Import inside the function to avoid import-time side-effects in the worker
    from .agents import run_incident_workflow
    from .cache import cache_delete
    from .db.engine import AsyncSessionLocal
    from .db.repository import (
        complete_agent_run,
        get_incident,
        update_incident,
    )

    clear_log_context()
    bind_log_context(incident_id=incident_id, run_id=run_id, user_id=user_id)
    logger.info("incident_execution_started", provider=provider, model_name=model_name)

    async with AsyncSessionLocal() as db:
        incident = await get_incident(db, incident_id)
        if incident is None:
            raise ValueError(f"Incident {incident_id!r} not found")

        result = run_incident_workflow(
            incident,
            provider=provider,
            model_name=model_name,
            user_id=user_id,
        )  # type: ignore[arg-type]

        await update_incident(
            db,
            incident.id,
            status="investigating",
            summary=result["summary"],
            open_actions=[result["next_action"]],
        )
        await complete_agent_run(db, run_id, summary=result["summary"])

    # Invalidate cache *after* the DB transaction is committed
    await cache_delete("incidents:all", f"incident:{incident_id}")

    logger.info("incident_execution_completed", graph_run_id=result["graph_run_id"])
    payload = {
        "incident_id": incident_id,
        "run_id": run_id,
        "status": result["status"],
        "graph_run_id": result["graph_run_id"],
        "summary": result["summary"],
        "next_action": result["next_action"],
    }
    clear_log_context()
    return payload
