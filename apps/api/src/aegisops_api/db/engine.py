from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def _make_engine():
    # Import settings lazily to avoid circular imports at module load time.
    from aegisops_api.settings import get_settings  # noqa: PLC0415

    settings = get_settings()
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

    For production, prefer running ``alembic upgrade head`` before startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
