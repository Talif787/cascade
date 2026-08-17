from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cascade.domain.serving.aggregate import ServingView
from cascade.domain.serving.value_objects import Column


@dataclass(frozen=True, slots=True)
class ColumnView:
    name: str
    type: str
    role: str
    nullable: bool

    @classmethod
    def from_vo(cls, column: Column) -> ColumnView:
        return cls(
            name=column.name,
            type=column.type.value,
            role=column.role.value,
            nullable=column.nullable,
        )


@dataclass(frozen=True, slots=True)
class ServingViewView:
    id: str
    name: str
    source_dataset_id: str
    engine: str
    columns: list[ColumnView]
    order_by: list[str]
    partition_by: str | None
    refresh_mode: str
    refresh_cron: str
    refresh_enabled: bool
    status: str
    last_sync_ref: str | None
    last_row_count: int | None
    last_synced_at: datetime | None
    description: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_aggregate(cls, view: ServingView) -> ServingViewView:
        return cls(
            id=str(view.id),
            name=str(view.name),
            source_dataset_id=str(view.source_dataset_id),
            engine=view.engine.value,
            columns=[ColumnView.from_vo(c) for c in view.schema.columns],
            order_by=list(view.schema.order_by),
            partition_by=view.schema.partition_by,
            refresh_mode=view.refresh_mode.value,
            refresh_cron=view.refresh_cron,
            refresh_enabled=view.refresh_enabled,
            status=view.status.value,
            last_sync_ref=view.last_sync_ref,
            last_row_count=view.last_row_count,
            last_synced_at=view.last_synced_at,
            description=view.description,
            version=view.version,
            created_at=view.created_at,
            updated_at=view.updated_at,
        )


@dataclass(frozen=True, slots=True)
class CatalogEntryView:
    id: str
    name: str
    engine: str
    columns: list[ColumnView]
    last_synced_at: datetime | None
    row_count: int | None

    @classmethod
    def from_aggregate(cls, view: ServingView) -> CatalogEntryView:
        return cls(
            id=str(view.id),
            name=str(view.name),
            engine=view.engine.value,
            columns=[ColumnView.from_vo(c) for c in view.schema.columns],
            last_synced_at=view.last_synced_at,
            row_count=view.last_row_count,
        )


@dataclass(frozen=True, slots=True)
class QueryResultView:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
