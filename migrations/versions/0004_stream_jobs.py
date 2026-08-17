"""stream jobs

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-15 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = (
    "defined",
    "submitted",
    "running",
    "restarting",
    "suspended",
    "failed",
    "completed",
    "cancelled",
)


def upgrade() -> None:
    status_list = ", ".join(f"'{value}'" for value in _STATUS_VALUES)
    op.create_table(
        "stream_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("source", postgresql.JSONB(), nullable=False),
        sa.Column("sink", postgresql.JSONB(), nullable=False),
        sa.Column("delivery_guarantee", sa.String(length=16), nullable=False),
        sa.Column("checkpoint_config", postgresql.JSONB(), nullable=False),
        sa.Column("restart_strategy", postgresql.JSONB(), nullable=False),
        sa.Column("parallelism", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("runtime_ref", sa.String(length=255), nullable=True),
        sa.Column("savepoint_location", sa.String(length=1024), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["data_contracts.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("name", name="uq_stream_jobs_name"),
        sa.CheckConstraint(f"status IN ({status_list})", name="ck_stream_jobs_status"),
        sa.CheckConstraint(
            "delivery_guarantee IN ('exactly_once', 'at_least_once')",
            name="ck_stream_jobs_delivery_guarantee",
        ),
    )
    op.create_index("ix_stream_jobs_status", "stream_jobs", ["status"])
    op.create_index("ix_stream_jobs_contract_id", "stream_jobs", ["contract_id"])
    op.create_index("ix_stream_jobs_created_at", "stream_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_stream_jobs_created_at", table_name="stream_jobs")
    op.drop_index("ix_stream_jobs_contract_id", table_name="stream_jobs")
    op.drop_index("ix_stream_jobs_status", table_name="stream_jobs")
    op.drop_table("stream_jobs")
