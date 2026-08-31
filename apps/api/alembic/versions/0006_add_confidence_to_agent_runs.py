"""Add confidence column to agent_runs table

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-31 14:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("confidence", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "confidence")
