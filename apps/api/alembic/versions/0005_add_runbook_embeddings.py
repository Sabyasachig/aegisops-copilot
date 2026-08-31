"""Add runbook_embeddings table for RAG knowledge base

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-31 13:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    # The pgvector extension is created by migration 0004; ensure it exists.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "runbook_embeddings",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("service", sa.String(128), nullable=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_path", sa.Text, nullable=False, server_default="api"),
        sa.Column(
            "embedding",
            sa.dialects.postgresql.ARRAY(sa.Float),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Cast to native pgvector type so cosine-distance operators are available.
    op.execute(
        f"ALTER TABLE runbook_embeddings "
        f"ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM}) USING embedding::vector"
    )

    op.create_index("ix_runbook_embeddings_service", "runbook_embeddings", ["service"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_runbook_embeddings_embedding_cosine "
        "ON runbook_embeddings USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_runbook_embeddings_embedding_cosine")
    op.drop_index("ix_runbook_embeddings_service", table_name="runbook_embeddings")
    op.drop_table("runbook_embeddings")
