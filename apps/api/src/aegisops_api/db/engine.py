from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def _make_engine():
    # Import settings lazily to avoid circular imports at module load time.
    from aegisops_api.settings import get_settings  # noqa: PLC0415

    settings = get_settings()

    # NullPool disables connection pooling, which avoids event-loop
    # binding issues when running under pytest's anyio backend.
    if os.getenv("AIOPS_TESTING") == "true":
        return create_async_engine(
            settings.database_url,
            echo=False,
            poolclass=NullPool,
        )

    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


engine = _make_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create all tables that do not yet exist.

    In testing mode (AIOPS_TESTING=true) the schema is dropped and recreated on
    every startup so that column additions are always reflected without running
    Alembic migrations against the test database.

    For production, prefer running ``alembic upgrade head`` before startup.
    """
    async with engine.begin() as conn:
        if os.getenv("AIOPS_TESTING") == "true":
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
