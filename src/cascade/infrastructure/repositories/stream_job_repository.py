from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.domain.processing.aggregate import StreamJob
from cascade.domain.processing.repository import (
    JobSortField,
    StreamJobQuery,
    StreamJobRepository,
)
from cascade.domain.processing.value_objects import JobName, StreamJobId
from cascade.infrastructure.database.models import StreamJobModel
from cascade.infrastructure.database.processing_mappers import (
    checkpoint_to_dict,
    job_to_model,
    model_to_job,
)

_SORT_COLUMNS = {
    JobSortField.NAME: StreamJobModel.name,
    JobSortField.STATUS: StreamJobModel.status,
    JobSortField.CREATED_AT: StreamJobModel.created_at,
    JobSortField.UPDATED_AT: StreamJobModel.updated_at,
}


class SqlAlchemyStreamJobRepository(StreamJobRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, job: StreamJob) -> None:
        self._session.add(job_to_model(job))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"job name {job.name!s} is already in use") from exc

    async def update(self, job: StreamJob) -> None:
        model = await self._session.get(StreamJobModel, job.id.value)
        if model is None or model.version != job.version:
            raise ConcurrencyError(f"job {job.id!s} was modified concurrently")
        model.status = job.status.value
        model.checkpoint_config = checkpoint_to_dict(job.checkpoint_config)
        model.runtime_ref = job.runtime_ref
        model.savepoint_location = job.savepoint_location
        model.description = job.description
        model.updated_at = job.updated_at
        model.version = job.version + 1
        await self._session.flush()
        job._version = model.version

    async def get(self, job_id: StreamJobId) -> StreamJob | None:
        model = await self._session.get(StreamJobModel, job_id.value)
        return model_to_job(model) if model is not None else None

    async def get_by_name(self, name: JobName) -> StreamJob | None:
        result = await self._session.execute(
            select(StreamJobModel).where(StreamJobModel.name == str(name))
        )
        model = result.scalar_one_or_none()
        return model_to_job(model) if model is not None else None

    async def exists_by_name(self, name: JobName) -> bool:
        result = await self._session.execute(
            select(func.count()).select_from(StreamJobModel).where(StreamJobModel.name == str(name))
        )
        return bool(result.scalar_one())

    async def list(self, query: StreamJobQuery) -> tuple[list[StreamJob], int]:
        base = select(StreamJobModel)
        if query.status is not None:
            base = base.where(StreamJobModel.status == query.status.value)
        if query.sink_kind is not None:
            base = base.where(StreamJobModel.sink["kind"].astext == query.sink_kind.value)
        if query.delivery_guarantee is not None:
            base = base.where(StreamJobModel.delivery_guarantee == query.delivery_guarantee.value)
        if query.contract_id is not None:
            base = base.where(StreamJobModel.contract_id == query.contract_id.value)

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
        return [model_to_job(model) for model in models], total
