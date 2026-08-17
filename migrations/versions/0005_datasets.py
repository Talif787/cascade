"""datasets

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-01 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = (
    "registered",
    "materializing",
    "materialized",
    "stale",
    "failed",
    "deprecated",
)
_LAYER_VALUES = ("bronze", "silver", "gold")
_QUALITY_VALUES = ("unknown", "passed", "failed")


def upgrade() -> None:
    status_list = ", ".join(f"'{v}'" for v in _STATUS_VALUES)
    layer_list = ", ".join(f"'{v}'" for v in _LAYER_VALUES)
    quality_list = ", ".join(f"'{v}'" for v in _QUALITY_VALUES)
    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=127), nullable=False),
        sa.Column("layer", sa.String(length=16), nullable=False),
        sa.Column("transformation", postgresql.JSONB(), nullable=False),
        sa.Column("upstreams", postgresql.JSONB(), nullable=False),
        sa.Column("schedule", postgresql.JSONB(), nullable=False),
        sa.Column("quality_checks", postgresql.JSONB(), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("quality_status", sa.String(length=16), nullable=False),
        sa.Column("last_run_ref", sa.String(length=255), nullable=True),
        sa.Column("last_row_count", sa.Integer(), nullable=True),
        sa.Column("last_materialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_quality_outcomes", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["data_contracts.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("name", name="uq_datasets_name"),
        sa.CheckConstraint(f"layer IN ({layer_list})", name="ck_datasets_layer"),
        sa.CheckConstraint(f"status IN ({status_list})", name="ck_datasets_status"),
        sa.CheckConstraint(
            f"quality_status IN ({quality_list})", name="ck_datasets_quality_status"
        ),
    )
    op.create_index("ix_datasets_layer", "datasets", ["layer"])
    op.create_index("ix_datasets_status", "datasets", ["status"])
    op.create_index("ix_datasets_contract_id", "datasets", ["contract_id"])
    op.create_index("ix_datasets_created_at", "datasets", ["created_at"])
    op.create_index(
        "ix_datasets_upstreams",
        "datasets",
        ["upstreams"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_datasets_upstreams", table_name="datasets")
    op.drop_index("ix_datasets_created_at", table_name="datasets")
    op.drop_index("ix_datasets_contract_id", table_name="datasets")
    op.drop_index("ix_datasets_status", table_name="datasets")
    op.drop_index("ix_datasets_layer", table_name="datasets")
    op.drop_table("datasets")
