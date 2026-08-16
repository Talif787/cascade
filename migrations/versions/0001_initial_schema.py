"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-01-15 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipelines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("source", postgresql.JSONB(), nullable=False),
        sa.Column("sink", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'archived')",
            name="ck_pipelines_status",
        ),
        sa.UniqueConstraint("name", name="uq_pipelines_name"),
    )
    op.create_index("ix_pipelines_status", "pipelines", ["status"])
    op.create_index("ix_pipelines_created_at", "pipelines", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_pipelines_created_at", table_name="pipelines")
    op.drop_index("ix_pipelines_status", table_name="pipelines")
    op.drop_table("pipelines")
