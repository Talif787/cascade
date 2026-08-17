from __future__ import annotations

import asyncio

import structlog

from cascade.application.common.errors import ConflictError
from cascade.application.contracts.commands import (
    FieldInput,
    RegisterContractCommand,
    SchemaInput,
)
from cascade.application.contracts.service import DataContractApplicationService
from cascade.application.pipelines.commands import ConnectorInput, RegisterPipelineCommand
from cascade.application.pipelines.service import PipelineApplicationService
from cascade.infrastructure.config import get_settings
from cascade.infrastructure.database.engine import create_engine, create_session_factory
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from cascade.infrastructure.logging import configure_logging
from cascade.infrastructure.registry.factory import build_schema_registry

_logger = structlog.get_logger("cascade.seed")

_SEEDS = [
    RegisterPipelineCommand(
        name="orders-cdc-to-lake",
        source=ConnectorInput(type="postgres_cdc", resource="public.orders"),
        sink=ConnectorInput(type="iceberg", resource="bronze.orders"),
        description="Change data capture from the orders table into the lakehouse.",
    ),
    RegisterPipelineCommand(
        name="clickstream-to-clickhouse",
        source=ConnectorInput(type="kafka_topic", resource="events.clickstream"),
        sink=ConnectorInput(type="clickhouse", resource="analytics.clickstream"),
        description="Real-time clickstream events served from ClickHouse.",
    ),
]

_CONTRACT_SEEDS = [
    RegisterContractCommand(
        name="orders-value",
        schema_format="avro",
        compatibility_mode="backward",
        schema=SchemaInput(
            fields=[
                FieldInput(name="order_id", type="long"),
                FieldInput(name="customer_id", type="long"),
                FieldInput(name="amount", type="double"),
                FieldInput(name="currency", type="string", has_default=True),
                FieldInput(name="created_at", type="timestamp"),
            ]
        ),
        description="Canonical schema for order events flowing into the lakehouse.",
    ),
]


async def _seed() -> None:
    settings = get_settings()
    configure_logging(settings)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    service = PipelineApplicationService(lambda: SqlAlchemyUnitOfWork(session_factory))
    contract_service = DataContractApplicationService(
        lambda: SqlAlchemyUnitOfWork(session_factory), build_schema_registry(settings)
    )
    try:
        for command in _SEEDS:
            try:
                view = await service.register_pipeline(command)
                _logger.info("seed_created", name=view.name, id=view.id)
            except ConflictError:
                _logger.info("seed_skipped", name=command.name)
        for contract_command in _CONTRACT_SEEDS:
            try:
                contract_view = await contract_service.register_contract(contract_command)
                _logger.info(
                    "seed_contract_created",
                    name=contract_view.name,
                    id=contract_view.id,
                )
            except ConflictError:
                _logger.info("seed_contract_skipped", name=contract_command.name)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_seed())
