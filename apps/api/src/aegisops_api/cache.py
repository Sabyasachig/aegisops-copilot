from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the shared async Redis client, creating it on first call."""
    global _client
    if _client is None:
        from aegisops_api.settings import get_settings  # noqa: PLC0415

        _client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def cache_get(key: str) -> Any | None:
    """Return a deserialized value from Redis, or ``None`` on miss or error."""
    try:
        raw = await get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    """Serialize *value* to JSON and store it with an expiry of *ttl* seconds."""
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        pass


async def cache_delete(*keys: str) -> None:
    """Delete one or more keys from Redis, ignoring errors."""
    try:
        if keys:
            await get_redis().delete(*keys)
    except Exception:
        pass


async def close_redis() -> None:
    """Close the shared Redis connection (called during app shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
