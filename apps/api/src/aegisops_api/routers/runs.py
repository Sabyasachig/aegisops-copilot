import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_operator
from ..cache import get_redis
from ..db.engine import get_db
from ..db.repository import get_run_by_id, list_runs_for_incident as _list_runs
from ..models import RejectRunRequest

router = APIRouter(tags=["runs"], dependencies=[Depends(get_current_user)])


@router.get("/runs/{incident_id}")
async def runs(incident_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    return {
        "incident_id": incident_id,
        "runs": [r.model_dump(mode="json") for r in await _list_runs(db, incident_id)],
    }


@router.post("/runs/{run_id}/approve")
async def approve_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(require_operator),
) -> dict:
    """Submit an approval decision for a run awaiting human review."""
    run = await get_run_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.status != "needs_human":
        raise HTTPException(
            status_code=409,
            detail=f"Run is not awaiting approval (current status: {run.status!r}).",
        )
    redis = get_redis()
    await redis.setex(
        f"approval_decision:{run_id}",
        3600,
        json.dumps({"action": "approve", "user": current_user}),
    )
    return {"run_id": run_id, "decision": "approved", "by": current_user}


@router.post("/runs/{run_id}/reject")
async def reject_run(
    run_id: str,
    body: RejectRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(require_operator),
) -> dict:
    """Reject a run awaiting human review, with an optional reason."""
    run = await get_run_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.status != "needs_human":
        raise HTTPException(
            status_code=409,
            detail=f"Run is not awaiting approval (current status: {run.status!r}).",
        )
    reason = (body.reason if body else "") or ""
    redis = get_redis()
    await redis.setex(
        f"approval_decision:{run_id}",
        3600,
        json.dumps({"action": "reject", "reason": reason, "user": current_user}),
    )
    return {"run_id": run_id, "decision": "rejected", "by": current_user}
