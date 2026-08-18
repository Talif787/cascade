from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.domain.governance.aggregate import ServiceLevelObjective
from cascade.domain.governance.repository import SloQuery, SloRepository, SloSortField
from cascade.domain.governance.value_objects import SloId, SloName, SloStatus
from cascade.infrastructure.database.governance_mappers import model_to_slo, slo_to_model
from cascade.infrastructure.database.models import SloModel

_SORT_COLUMNS = {
    SloSortField.NAME: SloModel.name,
    SloSortField.STATUS: SloModel.status,
    SloSortField.STATE: SloModel.state,
    SloSortField.CREATED_AT: SloModel.created_at,
    SloSortField.UPDATED_AT: SloModel.updated_at,
}


class SqlAlchemySloRepository(SloRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, slo: ServiceLevelObjective) -> None:
        self._session.add(slo_to_model(slo))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"SLO name {slo.name!s} is already in use") from exc

    async def update(self, slo: ServiceLevelObjective) -> None:
        model = await self._session.get(SloModel, slo.id.value)
        if model is None or model.version != slo.version:
            raise ConcurrencyError(f"SLO {slo.id!s} was modified concurrently")
        model.max_staleness_minutes = slo.target.max_staleness_minutes
        model.status = slo.status.value
        model.state = slo.state.value
        model.last_evaluated_at = slo.last_evaluated_at
        model.last_staleness_minutes = slo.last_staleness_minutes
        model.breach_count = slo.breach_count
        model.updated_at = slo.updated_at
        model.version = slo.version + 1
        await self._session.flush()
        slo._version = model.version

    async def get(self, slo_id: SloId) -> ServiceLevelObjective | None:
        model = await self._session.get(SloModel, slo_id.value)
        return model_to_slo(model) if model is not None else None

    async def get_by_name(self, name: SloName) -> ServiceLevelObjective | None:
        result = await self._session.execute(select(SloModel).where(SloModel.name == str(name)))
        model = result.scalar_one_or_none()
        return model_to_slo(model) if model is not None else None

    async def exists_by_name(self, name: SloName) -> bool:
        result = await self._session.execute(
            select(func.count()).select_from(SloModel).where(SloModel.name == str(name))
        )
        return bool(result.scalar_one())

    async def list(self, query: SloQuery) -> tuple[list[ServiceLevelObjective], int]:
        base = select(SloModel)
        if query.asset_kind is not None:
            base = base.where(SloModel.asset_kind == query.asset_kind.value)
        if query.status is not None:
            base = base.where(SloModel.status == query.status.value)
        if query.state is not None:
            base = base.where(SloModel.state == query.state.value)

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
        return [model_to_slo(model) for model in models], total

    async def list_active(self) -> Sequence[ServiceLevelObjective]:
        result = await self._session.execute(
            select(SloModel)
            .where(SloModel.status == SloStatus.ACTIVE.value)
            .order_by(SloModel.name.asc())
        )
        return [model_to_slo(model) for model in result.scalars().all()]
