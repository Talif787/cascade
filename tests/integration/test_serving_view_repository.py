from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

pytest.importorskip("testcontainers")

from datetime import UTC

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from cascade.domain.lakehouse.aggregate import Dataset
from cascade.domain.lakehouse.value_objects import (
    DatasetName,
    Materialization,
    MedallionLayer,
    Schedule,
    Transformation,
    TransformationEngine,
)
from cascade.domain.serving.aggregate import ServingView
from cascade.domain.serving.repository import ServingViewQuery
from cascade.domain.serving.value_objects import (
    ClickHouseEngine,
    Column,
    ColumnRole,
    ColumnType,
    ExposedSchema,
    RefreshMode,
    ServingStatus,
    ServingViewName,
)
from cascade.infrastructure.database.models import Base
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


def _gold_dataset() -> Dataset:
    return Dataset.register(
        name=DatasetName("gold.orders_daily"),
        layer=MedallionLayer.GOLD,
        transformation=Transformation(
            engine=TransformationEngine.DBT,
            identifier="gold_orders_daily",
            materialization=Materialization.TABLE,
        ),
        schedule=Schedule(cron="0 2 * * *"),
    )


def _view(source: Dataset, name: str = "analytics.orders_daily") -> ServingView:
    schema = ExposedSchema(
        columns=(
            Column(name="region", type=ColumnType.STRING, role=ColumnRole.DIMENSION),
            Column(name="revenue", type=ColumnType.FLOAT, role=ColumnRole.MEASURE),
        ),
        order_by=("region",),
    )
    return ServingView.register(
        name=ServingViewName(name),
        source_dataset_id=source.id,
        engine=ClickHouseEngine.SUMMING_MERGE_TREE,
        schema=schema,
        refresh_mode=RefreshMode.FULL,
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


async def test_add_and_get_round_trip(uow_factory: object) -> None:
    source = _gold_dataset()
    view = _view(source)
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.datasets.add(source)
        await uow.serving_views.add(view)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.serving_views.get(view.id)
    assert loaded is not None
    assert str(loaded.name) == "analytics.orders_daily"
    assert loaded.engine is ClickHouseEngine.SUMMING_MERGE_TREE
    assert loaded.source_dataset_id == source.id
    assert [c.name for c in loaded.schema.columns] == ["region", "revenue"]


async def test_update_persists_sync_state(uow_factory: object) -> None:
    from datetime import datetime

    source = _gold_dataset()
    view = _view(source, "analytics.clicks")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.datasets.add(source)
        await uow.serving_views.add(view)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.serving_views.get(view.id)
        assert loaded is not None
        loaded.begin_sync("s1")
        loaded.complete_sync("s1", 128, datetime.now(UTC))
        await uow.serving_views.update(loaded)
        await uow.commit()
        assert loaded.version == 1

    async with uow_factory() as uow:  # type: ignore[operator]
        again = await uow.serving_views.get(view.id)
    assert again is not None
    assert again.status is ServingStatus.READY
    assert again.last_row_count == 128


async def test_list_ready_only_returns_ready(uow_factory: object) -> None:
    from datetime import datetime

    source = _gold_dataset()
    ready = _view(source, "analytics.ready")
    pending = _view(source, "analytics.pending")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.datasets.add(source)
        await uow.serving_views.add(ready)
        await uow.serving_views.add(pending)
        loaded = await uow.serving_views.get(ready.id)
        assert loaded is not None
        loaded.begin_sync("s1")
        loaded.complete_sync("s1", 5, datetime.now(UTC))
        await uow.serving_views.update(loaded)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        views = await uow.serving_views.list_ready()
        _, total = await uow.serving_views.list(ServingViewQuery())
    assert [str(v.name) for v in views] == ["analytics.ready"]
    assert total == 2
