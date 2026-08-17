"""ingestion sources

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-01 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = (
    "registered",
    "provisioning",
    "running",
    "paused",
    "failed",
    "decommissioned",
)


def upgrade() -> None:
    status_list = ", ".join(f"'{value}'" for value in _STATUS_VALUES)
    op.create_table(
        "ingestion_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("connector_kind", sa.String(length=32), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("dead_letter_policy", postgresql.JSONB(), nullable=False),
        sa.Column("dead_letter_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_ref", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["data_contracts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id"], ["pipelines.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("name", name="uq_ingestion_sources_name"),
        sa.CheckConstraint(
            f"status IN ({status_list})", name="ck_ingestion_sources_status"
        ),
    )
    op.create_index("ix_ingestion_sources_status", "ingestion_sources", ["status"])
    op.create_index(
        "ix_ingestion_sources_connector_kind", "ingestion_sources", ["connector_kind"]
    )
    op.create_index(
        "ix_ingestion_sources_contract_id", "ingestion_sources", ["contract_id"]
    )
    op.create_index(
        "ix_ingestion_sources_created_at", "ingestion_sources", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_sources_created_at", table_name="ingestion_sources")
    op.drop_index("ix_ingestion_sources_contract_id", table_name="ingestion_sources")
    op.drop_index("ix_ingestion_sources_connector_kind", table_name="ingestion_sources")
    op.drop_index("ix_ingestion_sources_status", table_name="ingestion_sources")
    op.drop_table("ingestion_sources")
