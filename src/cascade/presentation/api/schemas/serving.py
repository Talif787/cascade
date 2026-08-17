from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cascade.application.serving.dto import (
    CatalogEntryView,
    QueryResultView,
    ServingViewView,
)


class ColumnPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=63, examples=["order_id"])
    type: str = Field(examples=["int"])
    role: str = Field(examples=["dimension"])
    nullable: bool = False


class RegisterServingViewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=127, examples=["analytics.orders_daily"])
    source_dataset_id: str = Field(examples=["9b3c9215-e635-4d07-a379-ca21864ebddb"])
    engine: str = Field(default="merge_tree", examples=["aggregating_merge_tree"])
    columns: list[ColumnPayload] = Field(min_length=1)
    order_by: list[str] = Field(min_length=1)
    partition_by: str | None = None
    refresh_mode: str = Field(default="full", examples=["full"])
    refresh_cron: str = Field(default="0 * * * *")
    refresh_enabled: bool = True
    description: str = Field(default="", max_length=1024)


class ChangeScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_cron: str = Field(examples=["0 6 * * *"])
    refresh_enabled: bool = True


class MeasurePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    aggregation: str = Field(examples=["sum"])


class FilterPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    op: str = Field(examples=["eq"])
    values: list[str] = Field(default_factory=list)


class RunQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimensions: list[str] = Field(default_factory=list)
    measures: list[MeasurePayload] = Field(default_factory=list)
    filters: list[FilterPayload] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=10_000)


class ColumnResponse(BaseModel):
    name: str
    type: str
    role: str
    nullable: bool


class ServingViewResponse(BaseModel):
    id: str
    name: str
    source_dataset_id: str
    engine: str
    columns: list[ColumnResponse]
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
    def from_view(cls, view: ServingViewView) -> ServingViewResponse:
        return cls(
            id=view.id,
            name=view.name,
            source_dataset_id=view.source_dataset_id,
            engine=view.engine,
            columns=[
                ColumnResponse(name=c.name, type=c.type, role=c.role, nullable=c.nullable)
                for c in view.columns
            ],
            order_by=view.order_by,
            partition_by=view.partition_by,
            refresh_mode=view.refresh_mode,
            refresh_cron=view.refresh_cron,
            refresh_enabled=view.refresh_enabled,
            status=view.status,
            last_sync_ref=view.last_sync_ref,
            last_row_count=view.last_row_count,
            last_synced_at=view.last_synced_at,
            description=view.description,
            version=view.version,
            created_at=view.created_at,
            updated_at=view.updated_at,
        )


class CatalogEntryResponse(BaseModel):
    id: str
    name: str
    engine: str
    columns: list[ColumnResponse]
    last_synced_at: datetime | None
    row_count: int | None

    @classmethod
    def from_view(cls, entry: CatalogEntryView) -> CatalogEntryResponse:
        return cls(
            id=entry.id,
            name=entry.name,
            engine=entry.engine,
            columns=[
                ColumnResponse(name=c.name, type=c.type, role=c.role, nullable=c.nullable)
                for c in entry.columns
            ],
            last_synced_at=entry.last_synced_at,
            row_count=entry.row_count,
        )


class CatalogResponse(BaseModel):
    entries: list[CatalogEntryResponse]


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int

    @classmethod
    def from_view(cls, view: QueryResultView) -> QueryResponse:
        return cls(columns=view.columns, rows=view.rows, row_count=view.row_count)
