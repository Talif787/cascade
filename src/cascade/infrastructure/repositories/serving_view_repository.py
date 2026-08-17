from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.domain.serving.aggregate import ServingView
from cascade.domain.serving.repository import (
    ServingViewQuery,
    ServingViewRepository,
    ServingViewSortField,
)
from cascade.domain.serving.value_objects import (
    ServingStatus,
    ServingViewId,
    ServingViewName,
)
from cascade.infrastructure.database.models import ServingViewModel
from cascade.infrastructure.database.serving_mappers import (
    model_to_serving_view,
    serving_view_to_model,
)

_SORT_COLUMNS = {
    ServingViewSortField.NAME: ServingViewModel.name,
    ServingViewSortField.STATUS: ServingViewModel.status,
    ServingViewSortField.CREATED_AT: ServingViewModel.created_at,
    ServingViewSortField.UPDATED_AT: ServingViewModel.updated_at,
}


class SqlAlchemyServingViewRepository(ServingViewRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, view: ServingView) -> None:
        self._session.add(serving_view_to_model(view))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"serving view name {view.name!s} is already in use") from exc

    async def update(self, view: ServingView) -> None:
        model = await self._session.get(ServingViewModel, view.id.value)
        if model is None or model.version != view.version:
            raise ConcurrencyError(f"serving view {view.id!s} was modified concurrently")
        model.status = view.status.value
        model.refresh_cron = view.refresh_cron
        model.refresh_enabled = view.refresh_enabled
        model.last_sync_ref = view.last_sync_ref
        model.last_row_count = view.last_row_count
        model.last_synced_at = view.last_synced_at
        model.synced_source_at = view.synced_source_at
        model.description = view.description
        model.updated_at = view.updated_at
        model.version = view.version + 1
        await self._session.flush()
        view._version = model.version

    async def get(self, view_id: ServingViewId) -> ServingView | None:
        model = await self._session.get(ServingViewModel, view_id.value)
        return model_to_serving_view(model) if model is not None else None

    async def get_by_name(self, name: ServingViewName) -> ServingView | None:
        result = await self._session.execute(
            select(ServingViewModel).where(ServingViewModel.name == str(name))
        )
        model = result.scalar_one_or_none()
        return model_to_serving_view(model) if model is not None else None

    async def exists_by_name(self, name: ServingViewName) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(ServingViewModel)
            .where(ServingViewModel.name == str(name))
        )
        return bool(result.scalar_one())

    async def list(self, query: ServingViewQuery) -> tuple[list[ServingView], int]:
        base = select(ServingViewModel)
        if query.status is not None:
            base = base.where(ServingViewModel.status == query.status.value)
        if query.engine is not None:
            base = base.where(ServingViewModel.engine == query.engine.value)
        if query.source_dataset_id is not None:
            base = base.where(ServingViewModel.source_dataset_id == query.source_dataset_id.value)

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
        return [model_to_serving_view(model) for model in models], total

    async def list_ready(self) -> Sequence[ServingView]:
        result = await self._session.execute(
            select(ServingViewModel)
            .where(ServingViewModel.status == ServingStatus.READY.value)
            .order_by(ServingViewModel.name.asc())
        )
        return [model_to_serving_view(model) for model in result.scalars().all()]
