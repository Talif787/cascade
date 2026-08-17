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
