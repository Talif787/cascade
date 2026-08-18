from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

_STATUS_VALUES = ("draft", "active", "paused", "archived")


class Base(DeclarativeBase):
    pass


class PipelineModel(Base):
    __tablename__ = "pipelines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    source: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sink: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {_STATUS_VALUES}", name="ck_pipelines_status"),
        Index("ix_pipelines_status", "status"),
        Index("ix_pipelines_created_at", "created_at"),
    )


_CONTRACT_STATUS_VALUES = ("active", "deprecated")
_VERSION_STATUS_VALUES = ("published", "deprecated")


class DataContractModel(Base):
    __tablename__ = "data_contracts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    schema_format: Mapped[str] = mapped_column(String(16), nullable=False)
    compatibility_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    schema_versions: Mapped[list[SchemaVersionModel]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="SchemaVersionModel.version",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(f"status IN {_CONTRACT_STATUS_VALUES}", name="ck_data_contracts_status"),
        Index("ix_data_contracts_status", "status"),
        Index("ix_data_contracts_created_at", "created_at"),
    )


class SchemaVersionModel(Base):
    __tablename__ = "schema_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_contracts.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    registry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    contract: Mapped[DataContractModel] = relationship(back_populates="schema_versions")

    __table_args__ = (
        UniqueConstraint("contract_id", "version", name="uq_schema_versions_contract_version"),
        CheckConstraint(f"status IN {_VERSION_STATUS_VALUES}", name="ck_schema_versions_status"),
        Index("ix_schema_versions_contract_id", "contract_id"),
    )


_SOURCE_STATUS_VALUES = (
    "registered",
    "provisioning",
    "running",
    "paused",
    "failed",
    "decommissioned",
)


class IngestionSourceModel(Base):
    __tablename__ = "ingestion_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    connector_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pipeline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    dead_letter_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dead_letter_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runtime_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {_SOURCE_STATUS_VALUES}", name="ck_ingestion_sources_status"),
        Index("ix_ingestion_sources_status", "status"),
        Index("ix_ingestion_sources_connector_kind", "connector_kind"),
        Index("ix_ingestion_sources_contract_id", "contract_id"),
        Index("ix_ingestion_sources_created_at", "created_at"),
    )


_JOB_STATUS_VALUES = (
    "defined",
    "submitted",
    "running",
    "restarting",
    "suspended",
    "failed",
    "completed",
    "cancelled",
)


class StreamJobModel(Base):
    __tablename__ = "stream_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    source: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sink: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    delivery_guarantee: Mapped[str] = mapped_column(String(16), nullable=False)
    checkpoint_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    restart_strategy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parallelism: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_contracts.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    runtime_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    savepoint_location: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {_JOB_STATUS_VALUES}", name="ck_stream_jobs_status"),
        CheckConstraint(
            "delivery_guarantee IN ('exactly_once', 'at_least_once')",
            name="ck_stream_jobs_delivery_guarantee",
        ),
        Index("ix_stream_jobs_status", "status"),
        Index("ix_stream_jobs_contract_id", "contract_id"),
        Index("ix_stream_jobs_created_at", "created_at"),
    )


_DATASET_STATUS_VALUES = (
    "registered",
    "materializing",
    "materialized",
    "stale",
    "failed",
    "deprecated",
)

_LAYER_VALUES = ("bronze", "silver", "gold")
_QUALITY_STATUS_VALUES = ("unknown", "passed", "failed")


class DatasetModel(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(127), nullable=False, unique=True)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)
    transformation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    upstreams: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    schedule: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    quality_checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_contracts.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(16), nullable=False)
    last_run_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_materialized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_quality_outcomes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"layer IN {_LAYER_VALUES}", name="ck_datasets_layer"),
        CheckConstraint(f"status IN {_DATASET_STATUS_VALUES}", name="ck_datasets_status"),
        CheckConstraint(
            f"quality_status IN {_QUALITY_STATUS_VALUES}", name="ck_datasets_quality_status"
        ),
        Index("ix_datasets_layer", "layer"),
        Index("ix_datasets_status", "status"),
        Index("ix_datasets_contract_id", "contract_id"),
        Index("ix_datasets_created_at", "created_at"),
        Index("ix_datasets_upstreams", "upstreams", postgresql_using="gin"),
    )


_SERVING_STATUS_VALUES = (
    "registered",
    "syncing",
    "ready",
    "stale",
    "failed",
    "retired",
)

_SERVING_ENGINE_VALUES = (
    "merge_tree",
    "replacing_merge_tree",
    "summing_merge_tree",
    "aggregating_merge_tree",
)


class ServingViewModel(Base):
    __tablename__ = "serving_views"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(127), nullable=False, unique=True)
    source_dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    order_by: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    partition_by: Mapped[str | None] = mapped_column(String(63), nullable=True)
    refresh_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    refresh_cron: Mapped[str] = mapped_column(String(128), nullable=False)
    refresh_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    last_sync_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_source_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {_SERVING_STATUS_VALUES}", name="ck_serving_views_status"),
        CheckConstraint(f"engine IN {_SERVING_ENGINE_VALUES}", name="ck_serving_views_engine"),
        Index("ix_serving_views_status", "status"),
        Index("ix_serving_views_source_dataset_id", "source_dataset_id"),
        Index("ix_serving_views_created_at", "created_at"),
    )


_ASSET_KIND_VALUES = (
    "pipeline",
    "ingestion_source",
    "stream_job",
    "dataset",
    "serving_view",
)

_SLO_STATUS_VALUES = ("active", "suspended", "retired")
_COMPLIANCE_STATE_VALUES = ("unknown", "meeting", "at_risk", "breached")
_SEVERITY_VALUES = ("low", "medium", "high", "critical")
_COST_CATEGORY_VALUES = ("compute", "storage", "transfer")


class SloModel(Base):
    __tablename__ = "freshness_slos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    asset_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    max_staleness_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_staleness_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    breach_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"asset_kind IN {_ASSET_KIND_VALUES}", name="ck_freshness_slos_asset_kind"),
        CheckConstraint(f"status IN {_SLO_STATUS_VALUES}", name="ck_freshness_slos_status"),
        CheckConstraint(f"state IN {_COMPLIANCE_STATE_VALUES}", name="ck_freshness_slos_state"),
        CheckConstraint(f"severity IN {_SEVERITY_VALUES}", name="ck_freshness_slos_severity"),
        Index("ix_freshness_slos_status", "status"),
        Index("ix_freshness_slos_state", "state"),
        Index("ix_freshness_slos_asset", "asset_kind", "asset_id"),
    )


class CostEntryModel(Base):
    __tablename__ = "cost_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    asset_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"asset_kind IN {_ASSET_KIND_VALUES}", name="ck_cost_entries_asset_kind"),
        CheckConstraint(f"category IN {_COST_CATEGORY_VALUES}", name="ck_cost_entries_category"),
        CheckConstraint("amount_cents >= 0", name="ck_cost_entries_amount"),
        Index("ix_cost_entries_asset", "asset_kind", "asset_id"),
        Index("ix_cost_entries_period_start", "period_start"),
        Index("ix_cost_entries_category", "category"),
    )


_COPILOT_STATUS_VALUES = ("asked", "translated", "rejected", "executed", "failed")


class CopilotQueryModel(Base):
    __tablename__ = "copilot_queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    view_id: Mapped[str] = mapped_column(String(64), nullable=False)
    view_name: Mapped[str] = mapped_column(String(127), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    translated: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {_COPILOT_STATUS_VALUES}", name="ck_copilot_queries_status"),
        Index("ix_copilot_queries_status", "status"),
        Index("ix_copilot_queries_view_id", "view_id"),
        Index("ix_copilot_queries_created_at", "created_at"),
    )
