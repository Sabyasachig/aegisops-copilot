from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

import redis

from .settings import get_settings


def incident_events_channel(incident_id: str) -> str:
    """Return the pub/sub channel used for SSE updates for one incident."""
    return f"aegisops:incident:{incident_id}:events"


def build_incident_event(event_type: str, **fields: Any) -> dict[str, Any]:
    """Build a normalized event payload consumed by the SSE endpoint."""
    payload: dict[str, Any] = {
        "event": event_type,
        "ts": datetime.now(UTC).isoformat(),
    }
    payload.update(fields)
    return payload


def publish_incident_event(incident_id: str, event_type: str, **fields: Any) -> None:
    """Publish one incident event to Redis pub/sub.

    Uses a short-lived synchronous client so this function can be called from
    both API and Celery worker paths, including synchronous graph callbacks.
    """
    settings = get_settings()
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        payload = build_incident_event(event_type, incident_id=incident_id, **fields)
        client.publish(incident_events_channel(incident_id), json.dumps(payload, default=str))
    finally:
        client.close()