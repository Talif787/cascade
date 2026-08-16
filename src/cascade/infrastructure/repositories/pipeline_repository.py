from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.domain.pipelines.aggregate import Pipeline
from cascade.domain.pipelines.repository import (
    PipelineQuery,
    PipelineRepository,
    PipelineSortField,
)
from cascade.domain.pipelines.value_objects import PipelineId, PipelineName
from cascade.infrastructure.database.mappers import (
    model_to_pipeline,
    pipeline_to_model,
    sink_to_dict,
    source_to_dict,
)
from cascade.infrastructure.database.models import PipelineModel

_SORT_COLUMNS = {
    PipelineSortField.NAME: PipelineModel.name,
    PipelineSortField.STATUS: PipelineModel.status,
    PipelineSortField.CREATED_AT: PipelineModel.created_at,
    PipelineSortField.UPDATED_AT: PipelineModel.updated_at,
}


class SqlAlchemyPipelineRepository(PipelineRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, pipeline: Pipeline) -> None:
        self._session.add(pipeline_to_model(pipeline))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"pipeline name {pipeline.name!s} is already in use") from exc

    async def update(self, pipeline: Pipeline) -> None:
        model = await self._session.get(PipelineModel, pipeline.id.value)
        if model is None or model.version != pipeline.version:
            raise ConcurrencyError(f"pipeline {pipeline.id!s} was modified concurrently")
        model.status = pipeline.status.value
        model.description = pipeline.description
        model.source = source_to_dict(pipeline.source)
        model.sink = sink_to_dict(pipeline.sink)
        model.updated_at = pipeline.updated_at
        model.version = pipeline.version + 1
        await self._session.flush()
        pipeline._version = model.version

    async def get(self, pipeline_id: PipelineId) -> Pipeline | None:
        model = await self._session.get(PipelineModel, pipeline_id.value)
        return model_to_pipeline(model) if model is not None else None

    async def get_by_name(self, name: PipelineName) -> Pipeline | None:
        result = await self._session.execute(
            select(PipelineModel).where(PipelineModel.name == str(name))
        )
        model = result.scalar_one_or_none()
        return model_to_pipeline(model) if model is not None else None

    async def exists_by_name(self, name: PipelineName) -> bool:
        result = await self._session.execute(
            select(func.count()).select_from(PipelineModel).where(PipelineModel.name == str(name))
        )
        return bool(result.scalar_one())

    async def list(self, query: PipelineQuery) -> tuple[list[Pipeline], int]:
        base = select(PipelineModel)
        if query.status is not None:
            base = base.where(PipelineModel.status == query.status.value)

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
        return [model_to_pipeline(model) for model in models], total
