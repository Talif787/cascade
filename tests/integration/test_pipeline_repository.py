from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

pytest.importorskip("testcontainers")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from cascade.application.common.errors import ConcurrencyError
from cascade.domain.pipelines.aggregate import Pipeline
from cascade.domain.pipelines.repository import PipelineQuery
from cascade.domain.pipelines.value_objects import (
    ConnectorType,
    PipelineName,
    SinkTarget,
    SinkType,
    SourceConnector,
)
from cascade.infrastructure.database.models import Base
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


def _pipeline(name: str = "orders-cdc") -> Pipeline:
    return Pipeline.register(
        name=PipelineName(name),
        source=SourceConnector(type=ConnectorType.POSTGRES_CDC, resource="public.orders"),
        sink=SinkTarget(type=SinkType.ICEBERG, resource="bronze.orders"),
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
    pipeline = _pipeline()
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.pipelines.add(pipeline)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.pipelines.get(pipeline.id)
    assert loaded is not None
    assert str(loaded.name) == "orders-cdc"
    assert loaded.source.type is ConnectorType.POSTGRES_CDC


async def test_update_increments_version(uow_factory: object) -> None:
    pipeline = _pipeline("clickstream")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.pipelines.add(pipeline)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.pipelines.get(pipeline.id)
        assert loaded is not None
        loaded.activate()
        await uow.pipelines.update(loaded)
        await uow.commit()
        assert loaded.version == 1


async def test_stale_update_raises_concurrency_error(uow_factory: object) -> None:
    pipeline = _pipeline("payments")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.pipelines.add(pipeline)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        first = await uow.pipelines.get(pipeline.id)
        assert first is not None
        first.activate()
        await uow.pipelines.update(first)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        stale = await uow.pipelines.get(pipeline.id)
        assert stale is not None
        stale._version = 0
        with pytest.raises(ConcurrencyError):
            await uow.pipelines.update(stale)


async def test_list_filters_and_counts(uow_factory: object) -> None:
    async with uow_factory() as uow:  # type: ignore[operator]
        for index in range(5):
            await uow.pipelines.add(_pipeline(f"pipeline-{index}"))
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        items, total = await uow.pipelines.list(PipelineQuery(offset=0, limit=2))
    assert total == 5
    assert len(items) == 2
