"""Celery tasks for AegisOps Copilot.

All tasks run the LangGraph incident workflow as a background job so that the
HTTP endpoint can return a ``202 Accepted`` immediately with a ``task_id``.
Callers poll ``GET /api/tasks/{task_id}`` to check progress.
"""

from __future__ import annotations

import asyncio

from .events import publish_incident_event
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


async def _wait_for_approval_decision(run_id: str, timeout_seconds: int) -> dict:
    """Poll Redis every 2 s for an approval decision written by the API.

    Returns a dict with at least ``{"action": "approve" | "reject" | "timeout"}``.
    """
    import json as _json
    import time

    from .cache import get_redis

    redis = get_redis()
    key = f"approval_decision:{run_id}"
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        raw = await redis.get(key)
        if raw:
            return _json.loads(raw)
        await asyncio.sleep(2)

    return {"action": "timeout"}


async def _execute_async(
    incident_id: str,
    run_id: str,
    user_id: str | None,
    provider: str,
    model_name: str,
) -> dict:
    """Async implementation — called from the Celery task via asyncio.run()."""
    import json as _json

    from .agents import run_incident_workflow
    from .cache import cache_delete, get_redis
    from .db.engine import AsyncSessionLocal
    from .db.repository import (
        complete_agent_run,
        get_incident,
        update_agent_run_status,
        update_incident,
    )
    from .settings import get_settings

    clear_log_context()
    bind_log_context(incident_id=incident_id, run_id=run_id, user_id=user_id)
    logger.info("incident_execution_started", provider=provider, model_name=model_name)
    publish_incident_event(incident_id, "workflow_started", run_id=run_id)

    async with AsyncSessionLocal() as db:
        incident = await get_incident(db, incident_id)
        if incident is None:
            raise ValueError(f"Incident {incident_id!r} not found")

        def _emit_workflow_event(event: str, payload: dict[str, str]) -> None:
            publish_incident_event(incident_id, event, run_id=run_id, **payload)

        # ── Agent memory retrieval (feature-flagged; lazy-imported) ──────────
        similar_ctx = ""
        settings = get_settings()
        if settings.memory_enabled:
            try:
                from .memory import (  # noqa: PLC0415
                    find_similar_incidents,
                    format_similar_incidents_for_prompt,
                )
                similar = await find_similar_incidents(
                    db,
                    query=f"{incident.title}\n{incident.summary}",
                    service=incident.service,
                )
                similar_ctx = format_similar_incidents_for_prompt(similar)
                if similar_ctx:
                    logger.info("similar_incidents_retrieved", count=len(similar))
            except Exception as exc:  # never fail the workflow on memory errors
                logger.warning("memory_retrieval_failed", error=str(exc))

        result = run_incident_workflow(
            incident,
            provider=provider,
            model_name=model_name,
            user_id=user_id,
            event_emitter=_emit_workflow_event,
            similar_incidents=similar_ctx or None,
        )  # type: ignore[arg-type]

        # ── Human-in-the-loop approval gate ──────────────────────────────────
        if result["status"] == "needs_human":
            thread_id: str = result["thread_id"]  # type: ignore[typeddict-item]
            redis = get_redis()

            await update_agent_run_status(db, run_id, "needs_human")
            await redis.setex(
                f"approval_pending:{run_id}",
                settings.approval_timeout_seconds + 300,
                _json.dumps({"thread_id": thread_id, "incident_id": incident_id}),
            )
            logger.info("workflow_awaiting_approval", run_id=run_id, thread_id=thread_id)
            publish_incident_event(incident_id, "approval_required", run_id=run_id)

            decision = await _wait_for_approval_decision(run_id, settings.approval_timeout_seconds)

            if decision["action"] == "approve":
                logger.info("workflow_approved", run_id=run_id)
                publish_incident_event(incident_id, "workflow_approved", run_id=run_id)
                result = run_incident_workflow(
                    incident,
                    provider=provider,
                    model_name=model_name,
                    user_id=user_id,
                    event_emitter=_emit_workflow_event,
                    resume_approved=True,
                    resume_thread_id=thread_id,
                )
            else:
                reason = decision.get("reason") or (
                    "No response within timeout."
                    if decision["action"] == "timeout"
                    else "Rejected by reviewer."
                )
                logger.info("workflow_not_approved", run_id=run_id,
                            action=decision["action"], reason=reason)
                publish_incident_event(incident_id, "workflow_rejected", run_id=run_id)
                result = {
                    "graph_run_id": result["graph_run_id"],
                    "status": "rejected",
                    "summary": f"Workflow rejected: {reason}",
                    "next_action": "Escalate to senior engineer or re-run with revised parameters.",
                }

            await redis.delete(f"approval_pending:{run_id}")
        # ── End approval gate ─────────────────────────────────────────────────

        await update_incident(
            db,
            incident.id,
            status="investigating",
            summary=result["summary"],
            open_actions=[result["next_action"]],
        )
        await complete_agent_run(db, run_id, summary=result["summary"], status=result["status"])

        # ── Agent memory persistence (feature-flagged) ───────────────────────
        if settings.memory_enabled and result["status"] == "done":
            try:
                from .memory import store_incident_embedding  # noqa: PLC0415
                await store_incident_embedding(
                    db,
                    incident_id=incident.id,
                    service=incident.service,
                    summary=result["summary"],
                )
            except Exception as exc:  # never fail on memory errors
                logger.warning("memory_persist_failed", error=str(exc))

    # Invalidate cache *after* the DB transaction is committed
    await cache_delete("incidents:all", f"incident:{incident_id}")

    logger.info("incident_execution_completed", graph_run_id=result["graph_run_id"])
    publish_incident_event(
        incident_id,
        "workflow_done",
        run_id=run_id,
        graph_run_id=result["graph_run_id"],
        status=result["status"],
    )
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
