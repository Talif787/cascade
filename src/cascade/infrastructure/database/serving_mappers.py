from __future__ import annotations

from typing import Any

from cascade.domain.lakehouse.value_objects import DatasetId
from cascade.domain.serving.aggregate import ServingView
from cascade.domain.serving.value_objects import (
    ClickHouseEngine,
    Column,
    ColumnRole,
    ColumnType,
    ExposedSchema,
    RefreshMode,
    ServingStatus,
    ServingViewId,
    ServingViewName,
)
from cascade.infrastructure.database.models import ServingViewModel


def _column_to_dict(column: Column) -> dict[str, Any]:
    return {
        "name": column.name,
        "type": column.type.value,
        "role": column.role.value,
        "nullable": column.nullable,
    }


def _column_from_dict(payload: dict[str, Any]) -> Column:
    return Column(
        name=payload["name"],
        type=ColumnType(payload["type"]),
        role=ColumnRole(payload["role"]),
        nullable=payload["nullable"],
    )


def serving_view_to_model(view: ServingView) -> ServingViewModel:
    return ServingViewModel(
        id=view.id.value,
        name=str(view.name),
        source_dataset_id=view.source_dataset_id.value,
        engine=view.engine.value,
        columns=[_column_to_dict(c) for c in view.schema.columns],
        order_by=list(view.schema.order_by),
        partition_by=view.schema.partition_by,
        refresh_mode=view.refresh_mode.value,
        refresh_cron=view.refresh_cron,
        refresh_enabled=view.refresh_enabled,
        status=view.status.value,
        last_sync_ref=view.last_sync_ref,
        last_row_count=view.last_row_count,
        last_synced_at=view.last_synced_at,
        synced_source_at=view.synced_source_at,
        description=view.description,
        version=view.version,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def model_to_serving_view(model: ServingViewModel) -> ServingView:
    schema = ExposedSchema(
        columns=tuple(_column_from_dict(c) for c in model.columns),
        order_by=tuple(model.order_by),
        partition_by=model.partition_by,
    )
    return ServingView(
        ServingViewId(model.id),
        name=ServingViewName(model.name),
        source_dataset_id=DatasetId(model.source_dataset_id),
        engine=ClickHouseEngine(model.engine),
        schema=schema,
        refresh_mode=RefreshMode(model.refresh_mode),
        refresh_cron=model.refresh_cron,
        refresh_enabled=model.refresh_enabled,
        status=ServingStatus(model.status),
        last_sync_ref=model.last_sync_ref,
        last_row_count=model.last_row_count,
        last_synced_at=model.last_synced_at,
        synced_source_at=model.synced_source_at,
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )
