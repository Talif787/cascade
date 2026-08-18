from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

pytest.importorskip("testcontainers")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from cascade.domain.copilot.aggregate import CopilotQuery
from cascade.domain.copilot.repository import CopilotQueryFilter
from cascade.domain.copilot.value_objects import (
    CopilotStatus,
    Question,
    TranslatedMeasure,
    TranslatedQuery,
)
from cascade.infrastructure.database.models import Base
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


def _executed_query() -> CopilotQuery:
    query = CopilotQuery.ask(
        question=Question("total revenue by region"),
        view_id="view-1",
        view_name="analytics.orders",
    )
    query.record_translation(
        TranslatedQuery(
            dimensions=("region",),
            measures=(TranslatedMeasure(column="revenue", aggregation="sum"),),
        )
    )
    query.record_execution(24)
    return query


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


async def test_round_trip_preserves_translation(uow_factory: object) -> None:
    query = _executed_query()
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.copilot_queries.add(query)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.copilot_queries.get(query.id)
    assert loaded is not None
    assert loaded.status is CopilotStatus.EXECUTED
    assert loaded.row_count == 24
    assert loaded.translated is not None
    assert loaded.translated.dimensions == ("region",)
    assert loaded.translated.measures[0].column == "revenue"


async def test_list_filters_by_status(uow_factory: object) -> None:
    executed = _executed_query()
    rejected = CopilotQuery.ask(
        question=Question("bad question"),
        view_id="view-1",
        view_name="analytics.orders",
    )
    rejected.reject("no known column matched")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.copilot_queries.add(executed)
        await uow.copilot_queries.add(rejected)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        items, total = await uow.copilot_queries.list(
            CopilotQueryFilter(status=CopilotStatus.EXECUTED)
        )
        recent = await uow.copilot_queries.recent(10)
    assert total == 1
    assert items[0].status is CopilotStatus.EXECUTED
    assert len(recent) == 2
