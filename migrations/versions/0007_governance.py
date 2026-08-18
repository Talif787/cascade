"""governance: freshness SLOs and cost entries

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-01 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ASSET_KIND_VALUES = (
    "pipeline",
    "ingestion_source",
    "stream_job",
    "dataset",
    "serving_view",
)
_STATUS_VALUES = ("active", "suspended", "retired")
_STATE_VALUES = ("unknown", "meeting", "at_risk", "breached")
_SEVERITY_VALUES = ("low", "medium", "high", "critical")
_CATEGORY_VALUES = ("compute", "storage", "transfer")


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    kinds = _in_list(_ASSET_KIND_VALUES)
    op.create_table(
        "freshness_slos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("asset_kind", sa.String(length=32), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("max_staleness_minutes", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_staleness_minutes", sa.Integer(), nullable=True),
        sa.Column("breach_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_freshness_slos_name"),
        sa.CheckConstraint(f"asset_kind IN ({kinds})", name="ck_freshness_slos_asset_kind"),
        sa.CheckConstraint(
            f"status IN ({_in_list(_STATUS_VALUES)})", name="ck_freshness_slos_status"
        ),
        sa.CheckConstraint(
            f"state IN ({_in_list(_STATE_VALUES)})", name="ck_freshness_slos_state"
        ),
        sa.CheckConstraint(
            f"severity IN ({_in_list(_SEVERITY_VALUES)})", name="ck_freshness_slos_severity"
        ),
    )
    op.create_index("ix_freshness_slos_status", "freshness_slos", ["status"])
    op.create_index("ix_freshness_slos_state", "freshness_slos", ["state"])
    op.create_index(
        "ix_freshness_slos_asset", "freshness_slos", ["asset_kind", "asset_id"]
    )

    op.create_table(
        "cost_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_kind", sa.String(length=32), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"asset_kind IN ({kinds})", name="ck_cost_entries_asset_kind"),
        sa.CheckConstraint(
            f"category IN ({_in_list(_CATEGORY_VALUES)})", name="ck_cost_entries_category"
        ),
        sa.CheckConstraint("amount_cents >= 0", name="ck_cost_entries_amount"),
    )
    op.create_index("ix_cost_entries_asset", "cost_entries", ["asset_kind", "asset_id"])
    op.create_index("ix_cost_entries_period_start", "cost_entries", ["period_start"])
    op.create_index("ix_cost_entries_category", "cost_entries", ["category"])


def downgrade() -> None:
    op.drop_index("ix_cost_entries_category", table_name="cost_entries")
    op.drop_index("ix_cost_entries_period_start", table_name="cost_entries")
    op.drop_index("ix_cost_entries_asset", table_name="cost_entries")
    op.drop_table("cost_entries")
    op.drop_index("ix_freshness_slos_asset", table_name="freshness_slos")
    op.drop_index("ix_freshness_slos_state", table_name="freshness_slos")
    op.drop_index("ix_freshness_slos_status", table_name="freshness_slos")
    op.drop_table("freshness_slos")
