from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

pytest.importorskip("testcontainers")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from cascade.domain.governance.aggregate import ServiceLevelObjective
from cascade.domain.governance.aggregate_cost import CostEntry
from cascade.domain.governance.repository import SloQuery
from cascade.domain.governance.value_objects import (
    AssetKind,
    AssetRef,
    ComplianceState,
    CostCategory,
    CostPeriod,
    FreshnessTarget,
    Money,
    SloName,
    SloStatus,
)
from cascade.infrastructure.database.models import Base
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


def _slo(name: str = "orders-freshness") -> ServiceLevelObjective:
    return ServiceLevelObjective.register(
        name=SloName(name),
        asset=AssetRef(kind=AssetKind.DATASET, asset_id="dataset-1"),
        target=FreshnessTarget(max_staleness_minutes=60),
    )


@pytest_asyncio.fixture
async def uow_factory() -> AsyncIterator[object]:
    with PostgresContainer("postgres:16-alpine") as container:
        url = container.get_connection_url().replace("psycopg2", "asyncpg")
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        yield lambda: SqlAlchemyUnitOfWork(session_factory)
        await engine.dispose()


async def test_slo_round_trip_and_evaluation(uow_factory: object) -> None:
    slo = _slo()
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.slos.add(slo)
        await uow.commit()

    now = datetime.now(UTC)
    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.slos.get(slo.id)
        assert loaded is not None
        loaded.evaluate(now - timedelta(minutes=120), now)
        await uow.slos.update(loaded)
        await uow.commit()
        assert loaded.version == 1

    async with uow_factory() as uow:  # type: ignore[operator]
        again = await uow.slos.get(slo.id)
    assert again is not None
    assert again.state is ComplianceState.BREACHED
    assert again.breach_count == 1


async def test_list_active_excludes_retired(uow_factory: object) -> None:
    active = _slo("active-slo")
    retired = _slo("retired-slo")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.slos.add(active)
        await uow.slos.add(retired)
        loaded = await uow.slos.get(retired.id)
        assert loaded is not None
        loaded.retire()
        await uow.slos.update(loaded)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        actives = await uow.slos.list_active()
        _, total = await uow.slos.list(SloQuery(status=SloStatus.ACTIVE))
    assert [str(s.name) for s in actives] == ["active-slo"]
    assert total == 1


async def test_cost_summary_groups_by_category_and_asset(uow_factory: object) -> None:
    now = datetime.now(UTC)
    period = CostPeriod(start=now - timedelta(days=1), end=now)
    entries = [
        CostEntry.record(
            asset=AssetRef(kind=AssetKind.DATASET, asset_id="d1"),
            category=CostCategory.COMPUTE,
            amount=Money(amount_cents=1000),
            period=period,
        ),
        CostEntry.record(
            asset=AssetRef(kind=AssetKind.DATASET, asset_id="d1"),
            category=CostCategory.STORAGE,
            amount=Money(amount_cents=250),
            period=period,
        ),
        CostEntry.record(
            asset=AssetRef(kind=AssetKind.SERVING_VIEW, asset_id="v1"),
            category=CostCategory.COMPUTE,
            amount=Money(amount_cents=500),
            period=period,
        ),
    ]
    async with uow_factory() as uow:  # type: ignore[operator]
        for entry in entries:
            await uow.cost_entries.add(entry)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        summary = await uow.cost_entries.summarize(None, None)
    assert summary.total_cents == 1750
    categories = {line.key: line.amount_cents for line in summary.by_category}
    assert categories["compute"] == 1500
    assert categories["storage"] == 250
    assets = {line.key: line.amount_cents for line in summary.by_asset}
    assert assets["dataset:d1"] == 1250
    assert assets["serving_view:v1"] == 500
