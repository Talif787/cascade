"""copilot queries

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-20 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = ("asked", "translated", "rejected", "executed", "failed")


def upgrade() -> None:
    status_list = ", ".join(f"'{v}'" for v in _STATUS_VALUES)
    op.create_table(
        "copilot_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("view_id", sa.String(length=64), nullable=False),
        sa.Column("view_name", sa.String(length=127), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("translated", postgresql.JSONB(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"status IN ({status_list})", name="ck_copilot_queries_status"
        ),
    )
    op.create_index("ix_copilot_queries_status", "copilot_queries", ["status"])
    op.create_index("ix_copilot_queries_view_id", "copilot_queries", ["view_id"])
    op.create_index("ix_copilot_queries_created_at", "copilot_queries", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_copilot_queries_created_at", table_name="copilot_queries")
    op.drop_index("ix_copilot_queries_view_id", table_name="copilot_queries")
    op.drop_index("ix_copilot_queries_status", table_name="copilot_queries")
    op.drop_table("copilot_queries")
