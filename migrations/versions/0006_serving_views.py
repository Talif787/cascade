"""serving views

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-15 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = ("registered", "syncing", "ready", "stale", "failed", "retired")
_ENGINE_VALUES = (
    "merge_tree",
    "replacing_merge_tree",
    "summing_merge_tree",
    "aggregating_merge_tree",
)


def upgrade() -> None:
    status_list = ", ".join(f"'{v}'" for v in _STATUS_VALUES)
    engine_list = ", ".join(f"'{v}'" for v in _ENGINE_VALUES)
    op.create_table(
        "serving_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=127), nullable=False),
        sa.Column("source_dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("order_by", postgresql.JSONB(), nullable=False),
        sa.Column("partition_by", sa.String(length=63), nullable=True),
        sa.Column("refresh_mode", sa.String(length=16), nullable=False),
        sa.Column("refresh_cron", sa.String(length=128), nullable=False),
        sa.Column("refresh_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_sync_ref", sa.String(length=255), nullable=True),
        sa.Column("last_row_count", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_source_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_dataset_id"], ["datasets.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("name", name="uq_serving_views_name"),
        sa.CheckConstraint(f"status IN ({status_list})", name="ck_serving_views_status"),
        sa.CheckConstraint(f"engine IN ({engine_list})", name="ck_serving_views_engine"),
    )
    op.create_index("ix_serving_views_status", "serving_views", ["status"])
    op.create_index(
        "ix_serving_views_source_dataset_id", "serving_views", ["source_dataset_id"]
    )
    op.create_index("ix_serving_views_created_at", "serving_views", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_serving_views_created_at", table_name="serving_views")
    op.drop_index("ix_serving_views_source_dataset_id", table_name="serving_views")
    op.drop_index("ix_serving_views_status", table_name="serving_views")
    op.drop_table("serving_views")
