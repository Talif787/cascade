from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cascade.application.common.errors import ConcurrencyError
from cascade.domain.copilot.aggregate import CopilotQuery
from cascade.domain.copilot.repository import (
    CopilotQueryFilter,
    CopilotQueryRepository,
    CopilotQuerySortField,
)
from cascade.domain.copilot.value_objects import CopilotQueryId
from cascade.infrastructure.database.copilot_mappers import (
    copilot_query_to_model,
    model_to_copilot_query,
)
from cascade.infrastructure.database.models import CopilotQueryModel

_SORT_COLUMNS = {
    CopilotQuerySortField.CREATED_AT: CopilotQueryModel.created_at,
    CopilotQuerySortField.UPDATED_AT: CopilotQueryModel.updated_at,
}


class SqlAlchemyCopilotQueryRepository(CopilotQueryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, query: CopilotQuery) -> None:
        self._session.add(copilot_query_to_model(query))
        await self._session.flush()

    async def update(self, query: CopilotQuery) -> None:
        model = await self._session.get(CopilotQueryModel, query.id.value)
        if model is None or model.version != query.version:
            raise ConcurrencyError(f"copilot query {query.id!s} was modified concurrently")
        model.status = query.status.value
        model.rejection_reason = query.rejection_reason
        model.row_count = query.row_count
        model.updated_at = query.updated_at
        model.version = query.version + 1
        await self._session.flush()
        query._version = model.version

    async def get(self, query_id: CopilotQueryId) -> CopilotQuery | None:
        model = await self._session.get(CopilotQueryModel, query_id.value)
        return model_to_copilot_query(model) if model is not None else None

    async def list(self, query_filter: CopilotQueryFilter) -> tuple[list[CopilotQuery], int]:
        base = select(CopilotQueryModel)
        if query_filter.status is not None:
            base = base.where(CopilotQueryModel.status == query_filter.status.value)
        if query_filter.view_id is not None:
            base = base.where(CopilotQueryModel.view_id == query_filter.view_id)

        total_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(total_result.scalar_one())

        column = _SORT_COLUMNS[query_filter.sort_by]
        order = column.desc() if query_filter.descending else column.asc()
        page_result = await self._session.execute(
            base.order_by(order).offset(query_filter.offset).limit(query_filter.limit)
        )
        models = page_result.scalars().all()
        return [model_to_copilot_query(model) for model in models], total

    async def recent(self, limit: int) -> Sequence[CopilotQuery]:
        result = await self._session.execute(
            select(CopilotQueryModel).order_by(CopilotQueryModel.created_at.desc()).limit(limit)
        )
        return [model_to_copilot_query(model) for model in result.scalars().all()]
