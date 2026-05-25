from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents import run_incident_workflow
from ..cache import cache_delete
from ..db.engine import get_db
from ..db.repository import (
    complete_agent_run,
    create_agent_run,
    get_incident,
    update_incident,
)
from ..models import ExecuteIncidentResponse
from ..settings import get_settings

router = APIRouter(tags=["execution"])


@router.post("/incidents/{incident_id}/execute", response_model=ExecuteIncidentResponse)
async def execute_incident(
    incident_id: str, db: AsyncSession = Depends(get_db)
) -> ExecuteIncidentResponse:
    incident = await get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    settings = get_settings()
    queued_run = await create_agent_run(
        db,
        incident_id=incident.id,
        agent_name="incident-ops",
        summary=f"Executing LangGraph workflow for {incident.title}",
    )
    result = run_incident_workflow(incident, provider=settings.llm_provider, model_name=settings.llm_model)

    await update_incident(
        db,
        incident.id,
        status="investigating",
        summary=result["summary"],
        open_actions=[result["next_action"]],
    )
    await complete_agent_run(db, queued_run.id, summary=result["summary"])

    # Invalidate cached incident data
    await cache_delete("incidents:all", f"incident:{incident_id}")

    return ExecuteIncidentResponse(
        incident_id=incident.id,
        status=result["status"],
        graph_run_id=result["graph_run_id"],
        summary=result["summary"],
        next_action=result["next_action"],
        run_id=queued_run.id,
    )
