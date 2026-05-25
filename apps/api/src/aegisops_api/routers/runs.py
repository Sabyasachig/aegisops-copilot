from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.engine import get_db
from ..db.repository import list_runs_for_incident as _list_runs

router = APIRouter(tags=["runs"])


@router.get("/runs/{incident_id}")
async def runs(incident_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    return {
        "incident_id": incident_id,
        "runs": [r.model_dump(mode="json") for r in await _list_runs(db, incident_id)],
    }
