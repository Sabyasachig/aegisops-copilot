"""Agent memory / RAG context store backed by pgvector.

Feature-flagged via ``AIOPS_MEMORY_ENABLED``.  When disabled (the default),
every public function short-circuits so tests and dev environments without
the pgvector extension keep working unchanged.

Design
------
- ``IncidentEmbeddingRow`` — SQLAlchemy model using the pgvector ``Vector``
  column type.  Defined at import time; the table is only created / queried
  when memory is enabled and Alembic has run.
- ``generate_embedding(text)`` — calls OpenAI's embeddings endpoint (or a
  deterministic dummy if no API key is configured).
- ``store_incident_embedding(db, incident_id, service, summary)`` — embeds the
  summary and inserts a row.
- ``find_similar_incidents(db, query, service, top_k)`` — retrieves the k
  nearest past incidents by cosine distance, optionally filtered by service.
- ``format_similar_incidents_for_prompt(items)`` — renders the retrieval
  result as a compact string suitable for injection into the ``assess`` prompt.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .logging_config import get_logger
from .settings import get_settings

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ORM
# ---------------------------------------------------------------------------


class MemoryBase(DeclarativeBase):
    """Separate declarative base so `incident_embeddings` is NOT created by
    the default ``Base.metadata.create_all`` used in tests.  In production,
    Alembic migration ``0004`` creates the extension and table.
    """


def _default_dim() -> int:
    """Read embedding dimension from settings; defaults to 1536."""
    try:
        return get_settings().memory_embedding_dim
    except Exception:
        return 1536


class IncidentEmbeddingRow(MemoryBase):
    __tablename__ = "incident_embeddings"
    __table_args__ = (Index("ix_incident_embeddings_service", "service"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(_default_dim()), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


@dataclass
class SimilarIncident:
    """Result item returned by :func:`find_similar_incidents`."""

    incident_id: str
    service: str
    summary: str
    distance: float


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------


def _deterministic_dummy_embedding(text: str, dim: int) -> list[float]:
    """Return a stable pseudo-embedding derived from a SHA-256 hash of *text*.

    Used when no OpenAI API key is configured (dev / test environments).
    Values are in [-1, 1); nearby texts produce different vectors, which is
    fine for smoke-testing storage and retrieval without external calls.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec: list[float] = []
    while len(vec) < dim:
        for byte in digest:
            vec.append((byte / 127.5) - 1.0)
            if len(vec) >= dim:
                break
        digest = hashlib.sha256(digest).digest()
    return vec[:dim]


def generate_embedding(text: str) -> list[float]:
    """Return an embedding vector for *text*.

    Uses OpenAI's embeddings endpoint when ``openai_api_key`` is set;
    otherwise returns a deterministic dummy vector.
    """
    settings = get_settings()
    dim = settings.memory_embedding_dim

    if not settings.openai_api_key:
        return _deterministic_dummy_embedding(text, dim)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.embeddings.create(model=settings.memory_embedding_model, input=text)
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning("embedding_fallback_to_dummy", error=str(exc))
        return _deterministic_dummy_embedding(text, dim)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def store_incident_embedding(
    db: AsyncSession,
    incident_id: str,
    service: str,
    summary: str,
) -> None:
    """Embed *summary* and persist a row.  No-op if memory is disabled."""
    settings = get_settings()
    if not settings.memory_enabled:
        return

    try:
        embedding = generate_embedding(summary)
        row = IncidentEmbeddingRow(
            id=f"EMB-{incident_id}-{int(datetime.now(UTC).timestamp())}",
            incident_id=incident_id,
            service=service,
            summary=summary,
            embedding=embedding,
        )
        db.add(row)
        await db.commit()
        logger.info("incident_embedding_stored", incident_id=incident_id, service=service)
    except Exception as exc:
        # Never fail the workflow because memory persistence failed.
        logger.warning("incident_embedding_store_failed", error=str(exc))
        await db.rollback()


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


async def find_similar_incidents(
    db: AsyncSession,
    query: str,
    service: str | None = None,
    top_k: int | None = None,
) -> list[SimilarIncident]:
    """Return the k nearest past incidents by cosine distance.

    Returns an empty list when memory is disabled, when no rows exist, or on
    any error \u2014 the workflow must never fail because of missing memory.
    """
    settings = get_settings()
    if not settings.memory_enabled:
        return []

    limit = top_k or settings.memory_top_k
    try:
        query_vec = generate_embedding(query)
        stmt = select(
            IncidentEmbeddingRow,
            IncidentEmbeddingRow.embedding.cosine_distance(query_vec).label("distance"),
        )
        if service:
            stmt = stmt.where(IncidentEmbeddingRow.service == service)
        stmt = stmt.order_by("distance").limit(limit)

        result = await db.execute(stmt)
        return [
            SimilarIncident(
                incident_id=row.incident_id,
                service=row.service,
                summary=row.summary,
                distance=float(distance),
            )
            for row, distance in result.all()
        ]
    except Exception as exc:
        logger.warning("similar_incident_lookup_failed", error=str(exc))
        return []


def format_similar_incidents_for_prompt(items: list[SimilarIncident]) -> str:
    """Render retrieved incidents as a compact block for LLM prompt injection."""
    if not items:
        return ""
    lines = ["Similar past incidents on this service:"]
    for i, item in enumerate(items, start=1):
        lines.append(f"  {i}. [{item.incident_id}] {item.summary} (distance={item.distance:.3f})")
    return "\n".join(lines)
