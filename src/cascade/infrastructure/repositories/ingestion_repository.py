from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.domain.ingestion.aggregate import IngestionSource
from cascade.domain.ingestion.repository import (
    IngestionSourceQuery,
    IngestionSourceRepository,
    SourceSortField,
)
from cascade.domain.ingestion.value_objects import IngestionSourceId, SourceName
from cascade.infrastructure.database.ingestion_mappers import (
    model_to_source,
    policy_to_dict,
    source_to_model,
)
from cascade.infrastructure.database.models import IngestionSourceModel

_SORT_COLUMNS = {
    SourceSortField.NAME: IngestionSourceModel.name,
    SourceSortField.STATUS: IngestionSourceModel.status,
    SourceSortField.CREATED_AT: IngestionSourceModel.created_at,
    SourceSortField.UPDATED_AT: IngestionSourceModel.updated_at,
}


class SqlAlchemyIngestionSourceRepository(IngestionSourceRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, source: IngestionSource) -> None:
        self._session.add(source_to_model(source))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"source name {source.name!s} is already in use") from exc

    async def update(self, source: IngestionSource) -> None:
        model = await self._session.get(IngestionSourceModel, source.id.value)
        if model is None or model.version != source.version:
            raise ConcurrencyError(f"source {source.id!s} was modified concurrently")
        model.status = source.status.value
        model.dead_letter_policy = policy_to_dict(source.dead_letter_policy)
        model.dead_letter_count = source.dead_letter_count
        model.runtime_ref = source.runtime_ref
        model.description = source.description
        model.updated_at = source.updated_at
        model.version = source.version + 1
        await self._session.flush()
        source._version = model.version

    async def get(self, source_id: IngestionSourceId) -> IngestionSource | None:
        model = await self._session.get(IngestionSourceModel, source_id.value)
        return model_to_source(model) if model is not None else None

    async def get_by_name(self, name: SourceName) -> IngestionSource | None:
        result = await self._session.execute(
            select(IngestionSourceModel).where(IngestionSourceModel.name == str(name))
        )
        model = result.scalar_one_or_none()
        return model_to_source(model) if model is not None else None

    async def exists_by_name(self, name: SourceName) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(IngestionSourceModel)
            .where(IngestionSourceModel.name == str(name))
        )
        return bool(result.scalar_one())

    async def list(self, query: IngestionSourceQuery) -> tuple[list[IngestionSource], int]:
        base = select(IngestionSourceModel)
        if query.status is not None:
            base = base.where(IngestionSourceModel.status == query.status.value)
        if query.connector_kind is not None:
            base = base.where(IngestionSourceModel.connector_kind == query.connector_kind.value)
        if query.contract_id is not None:
            base = base.where(IngestionSourceModel.contract_id == query.contract_id.value)

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
        return [model_to_source(model) for model in models], total
