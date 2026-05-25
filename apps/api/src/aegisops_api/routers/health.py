import sqlalchemy
from fastapi import APIRouter

from ..cache import get_redis
from ..db.engine import engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    checks: dict[str, str] = {}

    # PostgreSQL check
    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    # Redis check
    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {
        "status": overall,
        "service": "aegisops-api",
        "checks": checks,
    }
