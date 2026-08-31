"""Add pgvector extension and incident_embeddings table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-31 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    # pgvector extension must exist before the vector column is created.
    # Requires a Postgres image with pgvector available (e.g. pgvector/pgvector:pg16).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "incident_embeddings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(64),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("service", sa.String(128), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column(
            "embedding",
            sa.dialects.postgresql.ARRAY(sa.Float),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # NOTE: The `embedding` column is declared as ARRAY(Float) here so this
    # migration file does not require the pgvector Python package at Alembic
    # runtime.  The column is *altered* to the native pgvector `vector(N)`
    # type in the raw SQL below so cosine-distance operators work.
    op.execute(
        f"ALTER TABLE incident_embeddings "
        f"ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM}) USING embedding::vector"
    )

    op.create_index(
        "ix_incident_embeddings_incident_id",
        "incident_embeddings",
        ["incident_id"],
    )
    op.create_index(
        "ix_incident_embeddings_service",
        "incident_embeddings",
        ["service"],
    )
    # Approximate-nearest-neighbor index for cosine distance.  IVFFlat is
    # cheap to build; use HNSW in high-QPS deployments.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_incident_embeddings_embedding_cosine "
        "ON incident_embeddings USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_incident_embeddings_embedding_cosine")
    op.drop_index("ix_incident_embeddings_service", table_name="incident_embeddings")
    op.drop_index("ix_incident_embeddings_incident_id", table_name="incident_embeddings")
    op.drop_table("incident_embeddings")
    # We do NOT drop the extension on downgrade — other tables may use it.
