"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-25 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("service", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "open_actions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "incident_id",
            sa.String(64),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("artifact_url", sa.Text, nullable=True),
    )

    op.create_index("ix_agent_runs_incident_id", "agent_runs", ["incident_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_incident_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_table("incidents")
