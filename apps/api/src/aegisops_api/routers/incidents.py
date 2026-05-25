from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..cache import cache_get, cache_set
from ..db.engine import get_db
from ..db.repository import get_incident as _get_incident
from ..db.repository import list_incidents as _list_incidents

router = APIRouter(tags=["incidents"])


@router.get("/incidents")
async def incidents(db: AsyncSession = Depends(get_db)) -> dict:
    cached = await cache_get("incidents:all")
    if cached is not None:
        return {"incidents": cached, "source": "cache"}
    data = await _list_incidents(db)
    serialized = [i.model_dump(mode="json") for i in data]
    await cache_set("incidents:all", serialized, ttl=60)
    return {"incidents": serialized, "source": "db"}


@router.get("/incidents/{incident_id}")
async def incident(incident_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    cache_key = f"incident:{incident_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return {"incident": cached, "source": "cache"}
    data = await _get_incident(db, incident_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    serialized = data.model_dump(mode="json")
    await cache_set(cache_key, serialized, ttl=60)
    return {"incident": serialized, "source": "db"}
