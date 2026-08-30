import json
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_admin
from ..cache import cache_delete, cache_get, cache_set, get_redis
from ..db.engine import get_db
from ..db.repository import delete_incident as _delete_incident
from ..db.repository import get_incident as _get_incident
from ..db.repository import list_incidents as _list_incidents
from ..events import incident_events_channel
from ..settings import get_settings

router = APIRouter(tags=["incidents"], dependencies=[Depends(get_current_user)])


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


@router.delete(
    "/incidents/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
    summary="Delete an incident (admin only)",
)
async def delete_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    found = await _delete_incident(db, incident_id)
    if not found:
        raise HTTPException(status_code=404, detail="Incident not found.")
    await cache_delete("incidents:all")
    await cache_delete(f"incident:{incident_id}")


@router.get(
    "/incidents/{incident_id}/stream",
    summary="Stream real-time workflow events for one incident",
)
async def stream_incident_events(
    request: Request,
    incident_id: str,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """SSE endpoint for real-time workflow progress events."""
    if await _get_incident(db, incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    channel = incident_events_channel(incident_id)
    settings = get_settings()

    async def _event_generator():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(channel)
        last_send = monotonic()
        try:
            while True:
                if await request.is_disconnected():
                    break

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=settings.sse_stream_poll_seconds,
                )

                if message and message.get("type") == "message":
                    payload_raw = message.get("data")
                    try:
                        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
                    except json.JSONDecodeError:
                        payload = {"event": "message", "raw": str(payload_raw)}

                    event_type = str(payload.get("event", "message"))
                    data = json.dumps(payload, default=str)
                    yield f"event: {event_type}\ndata: {data}\n\n"
                    last_send = monotonic()
                    continue

                # Keep intermediary proxies and browsers from timing out idle SSE.
                if monotonic() - last_send >= settings.sse_keepalive_seconds:
                    yield ": keepalive\n\n"
                    last_send = monotonic()
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
