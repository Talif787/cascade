from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

pytest.importorskip("testcontainers")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from cascade.domain.contracts.aggregate import DataContract
from cascade.domain.contracts.repository import DataContractQuery
from cascade.domain.contracts.value_objects import (
    CompatibilityMode,
    ContractName,
    FieldType,
    SchemaDefinition,
    SchemaField,
    SchemaFormat,
    VersionStatus,
)
from cascade.infrastructure.database.models import Base
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration


def _schema(*fields: SchemaField) -> SchemaDefinition:
    return SchemaDefinition(fields=fields)


def _contract(name: str = "orders-value") -> DataContract:
    return DataContract.register(
        name=ContractName(name),
        schema_format=SchemaFormat.AVRO,
        compatibility_mode=CompatibilityMode.BACKWARD,
        initial_schema=_schema(SchemaField(name="id", type=FieldType.LONG)),
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
    contract = _contract()
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.contracts.add(contract)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.contracts.get(contract.id)
    assert loaded is not None
    assert str(loaded.name) == "orders-value"
    assert loaded.latest_version.version == 1


async def test_publish_version_persists_and_reconciles(uow_factory: object) -> None:
    contract = _contract("clickstream")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.contracts.add(contract)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.contracts.get(contract.id)
        assert loaded is not None
        loaded.publish_version(
            _schema(
                SchemaField(name="id", type=FieldType.LONG),
                SchemaField(name="ts", type=FieldType.TIMESTAMP, has_default=True),
            )
        )
        await uow.contracts.update(loaded)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        reloaded = await uow.contracts.get(contract.id)
    assert reloaded is not None
    assert reloaded.latest_version.version == 2
    assert len(reloaded.versions) == 2


async def test_deprecate_version_survives_round_trip(uow_factory: object) -> None:
    contract = _contract("payments")
    async with uow_factory() as uow:  # type: ignore[operator]
        await uow.contracts.add(contract)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        loaded = await uow.contracts.get(contract.id)
        assert loaded is not None
        loaded.deprecate_version(1)
        await uow.contracts.update(loaded)
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        reloaded = await uow.contracts.get(contract.id)
    assert reloaded is not None
    assert reloaded.get_version(1).status is VersionStatus.DEPRECATED


async def test_list_filters_and_counts(uow_factory: object) -> None:
    async with uow_factory() as uow:  # type: ignore[operator]
        for index in range(4):
            await uow.contracts.add(_contract(f"topic-{index}"))
        await uow.commit()

    async with uow_factory() as uow:  # type: ignore[operator]
        items, total = await uow.contracts.list(DataContractQuery(offset=0, limit=2))
    assert total == 4
    assert len(items) == 2
