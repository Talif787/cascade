from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

pytest.importorskip("testcontainers")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from cascade.domain.lakehouse.aggregate import Dataset
from cascade.domain.lakehouse.repository import DatasetQuery
from cascade.domain.lakehouse.value_objects import (
    DatasetName,
    DatasetRef,
    DatasetStatus,
    Materialization,
    MedallionLayer,
    QualityCheck,
    QualityCheckKind,
    QualityOutcome,
    Schedule,
    Transformation,
    TransformationEngine,
)
from cascade.infrastructure.database.models import Base
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


def _transformation() -> Transformation:
    return Transformation(
        engine=TransformationEngine.DBT,
        identifier="model_x",
        materialization=Materialization.TABLE,
    )


def _bronze(name: str = "bronze.orders") -> Dataset:
    return Dataset.register(
        name=DatasetName(name),
        layer=MedallionLayer.BRONZE,
        transformation=_transformation(),
        schedule=Schedule(cron="0 2 * * *"),
    )


def _silver(upstream: Dataset, name: str = "silver.orders") -> Dataset:
    return Dataset.register(
        name=DatasetName(name),
        layer=MedallionLayer.SILVER,
        transformation=_transformation(),
        schedule=Schedule(cron="0 3 * * *"),
        upstreams=(DatasetRef(dataset_id=upstream.id, name=upstream.name, layer=upstream.layer),),
        quality_checks=(QualityCheck(kind=QualityCheckKind.NOT_NULL, column="id"),),
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
    bronze = _bronze()
    silver = _silver(bronze)
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.datasets.add(bronze)
        await uow.datasets.add(silver)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.datasets.get(silver.id)
    assert loaded is not None
    assert loaded.layer is MedallionLayer.SILVER
    assert len(loaded.upstreams) == 1
    assert loaded.upstreams[0].dataset_id == bronze.id
    assert loaded.quality_checks[0].kind is QualityCheckKind.NOT_NULL


async def test_update_persists_materialization(uow_factory: object) -> None:
    bronze = _bronze("bronze.clicks")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.datasets.add(bronze)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.datasets.get(bronze.id)
        assert loaded is not None
        loaded.begin_materialization("run-1")
        loaded.complete_materialization(
            "run-1", 42, (QualityOutcome(name="row_count", passed=True),)
        )
        await uow.datasets.update(loaded)
        await uow.commit()
        assert loaded.version == 1

    async with uow_factory() as uow:  # type: ignore[operator]
        again = await uow.datasets.get(bronze.id)
    assert again is not None
    assert again.status is DatasetStatus.MATERIALIZED
    assert again.last_row_count == 42
    assert again.version == 1


async def test_list_dependents_uses_jsonb_containment(uow_factory: object) -> None:
    bronze = _bronze()
    silver = _silver(bronze)
    other = _bronze("bronze.other")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.datasets.add(bronze)
        await uow.datasets.add(silver)
        await uow.datasets.add(other)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        dependents = await uow.datasets.list_dependents(bronze.id)
    assert [str(d.name) for d in dependents] == ["silver.orders"]


async def test_list_filters_by_layer(uow_factory: object) -> None:
    bronze = _bronze()
    silver = _silver(bronze)
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.datasets.add(bronze)
        await uow.datasets.add(silver)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        datasets, total = await uow.datasets.list(DatasetQuery(layer=MedallionLayer.SILVER))
    assert total == 1
    assert str(datasets[0].name) == "silver.orders"
