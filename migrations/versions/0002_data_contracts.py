"""data contracts and schema versions

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-01 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("schema_format", sa.String(length=16), nullable=False),
        sa.Column("compatibility_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'deprecated')", name="ck_data_contracts_status"
        ),
        sa.UniqueConstraint("name", name="uq_data_contracts_name"),
    )
    op.create_index("ix_data_contracts_status", "data_contracts", ["status"])
    op.create_index("ix_data_contracts_created_at", "data_contracts", ["created_at"])

    op.create_table(
        "schema_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["data_contracts.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "contract_id", "version", name="uq_schema_versions_contract_version"
        ),
        sa.CheckConstraint(
            "status IN ('published', 'deprecated')", name="ck_schema_versions_status"
        ),
    )
    op.create_index("ix_schema_versions_contract_id", "schema_versions", ["contract_id"])


def downgrade() -> None:
    op.drop_index("ix_schema_versions_contract_id", table_name="schema_versions")
    op.drop_table("schema_versions")
    op.drop_index("ix_data_contracts_created_at", table_name="data_contracts")
    op.drop_index("ix_data_contracts_status", table_name="data_contracts")
    op.drop_table("data_contracts")
