from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from cascade.domain.governance.aggregate_cost import CostEntry
from cascade.domain.governance.repository import (
    CostEntryRepository,
    CostSummary,
    CostSummaryLine,
)
from cascade.domain.governance.value_objects import AssetRef, CostEntryId
from cascade.infrastructure.database.governance_mappers import (
    cost_entry_to_model,
    model_to_cost_entry,
)
from cascade.infrastructure.database.models import CostEntryModel


class SqlAlchemyCostEntryRepository(CostEntryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: CostEntry) -> None:
        self._session.add(cost_entry_to_model(entry))
        await self._session.flush()

    async def get(self, entry_id: CostEntryId) -> CostEntry | None:
        model = await self._session.get(CostEntryModel, entry_id.value)
        return model_to_cost_entry(model) if model is not None else None

    async def list_for_asset(self, asset: AssetRef) -> Sequence[CostEntry]:
        result = await self._session.execute(
            select(CostEntryModel)
            .where(CostEntryModel.asset_kind == asset.kind.value)
            .where(CostEntryModel.asset_id == asset.asset_id)
            .order_by(CostEntryModel.period_start.desc())
        )
        return [model_to_cost_entry(model) for model in result.scalars().all()]

    async def summarize(
        self, window_start: datetime | None, window_end: datetime | None
    ) -> CostSummary:
        filters: list[ColumnElement[bool]] = []
        if window_start is not None:
            filters.append(CostEntryModel.period_start >= window_start)
        if window_end is not None:
            filters.append(CostEntryModel.period_end <= window_end)

        total_stmt = select(func.coalesce(func.sum(CostEntryModel.amount_cents), 0))
        for condition in filters:
            total_stmt = total_stmt.where(condition)
        total_result = await self._session.execute(total_stmt)
        total = int(total_result.scalar_one())

        by_category = await self._grouped(
            cast("ColumnElement[str]", CostEntryModel.category), filters
        )
        asset_key = cast(
            "ColumnElement[str]",
            func.concat(CostEntryModel.asset_kind, ":", CostEntryModel.asset_id),
        )
        by_asset = await self._grouped(asset_key, filters)
        return CostSummary(total_cents=total, by_category=by_category, by_asset=by_asset)

    async def _grouped(
        self,
        key_column: ColumnElement[str],
        filters: Sequence[ColumnElement[bool]],
    ) -> tuple[CostSummaryLine, ...]:
        stmt = select(key_column, func.coalesce(func.sum(CostEntryModel.amount_cents), 0))
        for condition in filters:
            stmt = stmt.where(condition)
        stmt = stmt.group_by(key_column).order_by(func.sum(CostEntryModel.amount_cents).desc())
        result = await self._session.execute(stmt)
        return tuple(
            CostSummaryLine(key=str(row[0]), amount_cents=int(row[1])) for row in result.all()
        )
