from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

pytest.importorskip("testcontainers")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from cascade.domain.contracts.aggregate import DataContract
from cascade.domain.contracts.value_objects import (
    CompatibilityMode,
    ContractName,
    FieldType,
    SchemaDefinition,
    SchemaField,
    SchemaFormat,
)
from cascade.domain.ingestion.aggregate import IngestionSource
from cascade.domain.ingestion.repository import IngestionSourceQuery
from cascade.domain.ingestion.value_objects import (
    ConnectorConfig,
    ConnectorKind,
    DeadLetterPolicy,
    FailureAction,
    SourceName,
    SourceStatus,
)
from cascade.infrastructure.database.models import Base
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


def _contract(name: str = "orders-value") -> DataContract:
    return DataContract.register(
        name=ContractName(name),
        schema_format=SchemaFormat.AVRO,
        compatibility_mode=CompatibilityMode.BACKWARD,
        initial_schema=SchemaDefinition(fields=(SchemaField(name="id", type=FieldType.LONG),)),
    )


def _source(contract: DataContract, name: str = "orders-postgres-cdc") -> IngestionSource:
    return IngestionSource.register(
        name=SourceName(name),
        connector_kind=ConnectorKind.POSTGRES_CDC,
        config=ConnectorConfig(options={"database.hostname": "db"}),
        contract_id=contract.id,
        dead_letter_policy=DeadLetterPolicy(
            on_failure=FailureAction.DEAD_LETTER, dlq_topic="orders.dlq"
        ),
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


async def _seed_contract(uow_factory: object, name: str = "orders-value") -> DataContract:
    contract = _contract(name)
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.contracts.add(contract)
        await uow.commit()
    return contract


async def test_add_and_get_round_trip(uow_factory: object) -> None:
    contract = await _seed_contract(uow_factory)
    source = _source(contract)
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.ingestion_sources.add(source)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.ingestion_sources.get(source.id)
    assert loaded is not None
    assert str(loaded.name) == "orders-postgres-cdc"
    assert loaded.contract_id == contract.id
    assert loaded.status is SourceStatus.REGISTERED


async def test_update_reconciles_version(uow_factory: object) -> None:
    contract = await _seed_contract(uow_factory, "clickstream")
    source = _source(contract, "clicks-cdc")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.ingestion_sources.add(source)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.ingestion_sources.get(source.id)
        assert loaded is not None
        loaded.begin_provisioning()
        loaded.mark_running("cascade.postgres_cdc.clicks-cdc")
        await uow.ingestion_sources.update(loaded)
        await uow.commit()
        assert loaded.version == 1

    async with uow_factory() as uow:  # type: ignore[operator]
        again = await uow.ingestion_sources.get(source.id)
    assert again is not None
    assert again.status is SourceStatus.RUNNING
    assert again.runtime_ref == "cascade.postgres_cdc.clicks-cdc"
    assert again.version == 1


async def test_list_filters_by_kind(uow_factory: object) -> None:
    contract = await _seed_contract(uow_factory, "events")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.ingestion_sources.add(_source(contract, "cdc-one"))
        await uow.ingestion_sources.add(_source(contract, "cdc-two"))
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        sources, total = await uow.ingestion_sources.list(
            IngestionSourceQuery(connector_kind=ConnectorKind.POSTGRES_CDC)
        )
    assert total == 2
    assert {str(s.name) for s in sources} == {"cdc-one", "cdc-two"}
