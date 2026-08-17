from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.domain.lakehouse.aggregate import Dataset
from cascade.domain.lakehouse.repository import (
    DatasetQuery,
    DatasetRepository,
    DatasetSortField,
)
from cascade.domain.lakehouse.value_objects import DatasetId, DatasetName
from cascade.infrastructure.database.lakehouse_mappers import (
    dataset_to_model,
    model_to_dataset,
)
from cascade.infrastructure.database.models import DatasetModel

_SORT_COLUMNS = {
    DatasetSortField.NAME: DatasetModel.name,
    DatasetSortField.LAYER: DatasetModel.layer,
    DatasetSortField.STATUS: DatasetModel.status,
    DatasetSortField.CREATED_AT: DatasetModel.created_at,
    DatasetSortField.UPDATED_AT: DatasetModel.updated_at,
}


class SqlAlchemyDatasetRepository(DatasetRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, dataset: Dataset) -> None:
        self._session.add(dataset_to_model(dataset))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"dataset name {dataset.name!s} is already in use") from exc

    async def update(self, dataset: Dataset) -> None:
        model = await self._session.get(DatasetModel, dataset.id.value)
        if model is None or model.version != dataset.version:
            raise ConcurrencyError(f"dataset {dataset.id!s} was modified concurrently")
        model.schedule = {
            "cron": dataset.schedule.cron,
            "timezone": dataset.schedule.timezone,
            "enabled": dataset.schedule.enabled,
        }
        model.status = dataset.status.value
        model.quality_status = dataset.quality_status.value
        model.last_run_ref = dataset.last_run_ref
        model.last_row_count = dataset.last_row_count
        model.last_materialized_at = dataset.last_materialized_at
        model.last_quality_outcomes = [
            {"name": o.name, "passed": o.passed, "detail": o.detail}
            for o in dataset.last_quality_outcomes
        ]
        model.description = dataset.description
        model.updated_at = dataset.updated_at
        model.version = dataset.version + 1
        await self._session.flush()
        dataset._version = model.version

    async def get(self, dataset_id: DatasetId) -> Dataset | None:
        model = await self._session.get(DatasetModel, dataset_id.value)
        return model_to_dataset(model) if model is not None else None

    async def get_by_name(self, name: DatasetName) -> Dataset | None:
        result = await self._session.execute(
            select(DatasetModel).where(DatasetModel.name == str(name))
        )
        model = result.scalar_one_or_none()
        return model_to_dataset(model) if model is not None else None

    async def exists_by_name(self, name: DatasetName) -> bool:
        result = await self._session.execute(
            select(func.count()).select_from(DatasetModel).where(DatasetModel.name == str(name))
        )
        return bool(result.scalar_one())

    async def list(self, query: DatasetQuery) -> tuple[list[Dataset], int]:
        base = select(DatasetModel)
        if query.layer is not None:
            base = base.where(DatasetModel.layer == query.layer.value)
        if query.status is not None:
            base = base.where(DatasetModel.status == query.status.value)
        if query.quality_status is not None:
            base = base.where(DatasetModel.quality_status == query.quality_status.value)
        if query.contract_id is not None:
            base = base.where(DatasetModel.contract_id == query.contract_id.value)

        total_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(total_result.scalar_one())

        column = _SORT_COLUMNS[query.sort_by]
        order = column.desc() if query.descending else column.asc()
        page_result = await self._session.execute(
            base.order_by(order).offset(query.offset).limit(query.limit)
        )
        models = page_result.scalars().all()
        return [model_to_dataset(model) for model in models], total

    async def list_dependents(self, dataset_id: DatasetId) -> Sequence[Dataset]:
        needle = json.dumps([{"id": str(dataset_id)}])
        result = await self._session.execute(
            select(DatasetModel).where(
                text("datasets.upstreams @> cast(:needle as jsonb)").bindparams(needle=needle)
            )
        )
        return [model_to_dataset(model) for model in result.scalars().all()]
