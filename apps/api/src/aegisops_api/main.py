from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .cache import close_redis, get_redis
from .db.engine import AsyncSessionLocal, init_db
from .db.repository import create_incident, get_incident
from .routers.execute import router as execute_router
from .routers.health import router as health_router
from .routers.incidents import router as incidents_router
from .routers.providers import router as providers_router
from .routers.runs import router as runs_router
from .routers.tasks import router as tasks_router
from .routers.webhooks import router as webhooks_router
from .settings import get_settings
from .store import incidents as _seed_incidents  # seed data only


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ── Startup ──────────────────────────────────────────────────────────────
    await init_db()        # create tables if not present (Alembic owns this in prod)
    await _seed_db()       # insert default incidents if the table is empty
    get_redis()            # establish Redis connection pool
    yield
    # ── Shutdown ─────────────────────────────────────────────────────────────
    await close_redis()


async def _seed_db() -> None:
    """Insert the bundled sample incidents the first time the DB is empty."""
    async with AsyncSessionLocal() as db:
        for incident in _seed_incidents:
            if await get_incident(db, incident.id) is None:
                await create_incident(db, incident)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api")
    app.include_router(incidents_router, prefix="/api")
    app.include_router(runs_router, prefix="/api")
    app.include_router(execute_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")
    app.include_router(providers_router, prefix="/api")
    app.include_router(webhooks_router, prefix="/api")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("aegisops_api.main:app", host=settings.api_host, port=settings.api_port, reload=True)

