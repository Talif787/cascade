from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

pytest.importorskip("testcontainers")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from cascade.domain.processing.aggregate import StreamJob
from cascade.domain.processing.repository import StreamJobQuery
from cascade.domain.processing.value_objects import (
    CheckpointConfig,
    DeliveryGuarantee,
    JobName,
    JobSink,
    JobSource,
    JobStatus,
    RestartStrategy,
    SinkKind,
    SourceKind,
)
from cascade.infrastructure.database.models import Base
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


def _job(name: str = "orders-enrichment", *, sink_kind: SinkKind = SinkKind.ICEBERG) -> StreamJob:
    guarantee = (
        DeliveryGuarantee.EXACTLY_ONCE
        if sink_kind is SinkKind.ICEBERG
        else DeliveryGuarantee.AT_LEAST_ONCE
    )
    return StreamJob.define(
        name=JobName(name),
        source=JobSource(kind=SourceKind.KAFKA_TOPIC, resource="events.orders"),
        sink=JobSink(kind=sink_kind, resource="lake.silver.orders"),
        delivery_guarantee=guarantee,
        checkpoint_config=CheckpointConfig(interval_ms=30_000),
        restart_strategy=RestartStrategy(),
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
    job = _job()
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.stream_jobs.add(job)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.stream_jobs.get(job.id)
    assert loaded is not None
    assert str(loaded.name) == "orders-enrichment"
    assert loaded.sink.kind is SinkKind.ICEBERG
    assert loaded.delivery_guarantee is DeliveryGuarantee.EXACTLY_ONCE
    assert loaded.status is JobStatus.DEFINED


async def test_update_persists_lifecycle_and_savepoint(uow_factory: object) -> None:
    job = _job("clicks-agg")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.stream_jobs.add(job)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.stream_jobs.get(job.id)
        assert loaded is not None
        loaded.submit("flink-42")
        loaded.mark_running()
        loaded.suspend("s3://savepoints/flink-42/sp-1")
        await uow.stream_jobs.update(loaded)
        await uow.commit()
        assert loaded.version == 1

    async with uow_factory() as uow:  # type: ignore[operator]
        again = await uow.stream_jobs.get(job.id)
    assert again is not None
    assert again.status is JobStatus.SUSPENDED
    assert again.runtime_ref == "flink-42"
    assert again.savepoint_location == "s3://savepoints/flink-42/sp-1"
    assert again.version == 1


async def test_list_filters_by_sink_kind(uow_factory: object) -> None:
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.stream_jobs.add(_job("iceberg-job", sink_kind=SinkKind.ICEBERG))
        await uow.stream_jobs.add(_job("kafka-job", sink_kind=SinkKind.KAFKA_TOPIC))
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        jobs, total = await uow.stream_jobs.list(StreamJobQuery(sink_kind=SinkKind.ICEBERG))
    assert total == 1
    assert str(jobs[0].name) == "iceberg-job"
