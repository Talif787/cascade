from __future__ import annotations

import asyncio

import structlog

from cascade.application.common.errors import ConflictError
from cascade.application.contracts.commands import (
    FieldInput,
    RegisterContractCommand,
    SchemaInput,
)
from cascade.application.contracts.queries import ListContractsQuery
from cascade.application.contracts.service import DataContractApplicationService
from cascade.application.ingestion.commands import DeadLetterInput, RegisterSourceCommand
from cascade.application.ingestion.service import IngestionApplicationService
from cascade.application.pipelines.commands import ConnectorInput, RegisterPipelineCommand
from cascade.application.pipelines.service import PipelineApplicationService
from cascade.application.processing.commands import (
    CheckpointInput,
    DefineJobCommand,
    EndpointInput,
)
from cascade.application.processing.service import StreamProcessingApplicationService
from cascade.infrastructure.config import get_settings
from cascade.infrastructure.connect.factory import build_connector_runtime
from cascade.infrastructure.database.engine import create_engine, create_session_factory
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from cascade.infrastructure.flink.factory import build_flink_runtime
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
    ingestion_service = IngestionApplicationService(
        lambda: SqlAlchemyUnitOfWork(session_factory), build_connector_runtime(settings)
    )
    processing_service = StreamProcessingApplicationService(
        lambda: SqlAlchemyUnitOfWork(session_factory), build_flink_runtime(settings)
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

        orders_contract_id = await _resolve_contract_id(contract_service, "orders-value")
        if orders_contract_id is not None:
            try:
                source_view = await ingestion_service.register_source(
                    RegisterSourceCommand(
                        name="orders-postgres-cdc",
                        connector_kind="postgres_cdc",
                        config={
                            "database.hostname": "postgres",
                            "database.dbname": "cascade",
                            "table.include.list": "public.orders",
                        },
                        contract_id=orders_contract_id,
                        dead_letter=DeadLetterInput(
                            on_failure="dead_letter", dlq_topic="orders.dlq", tolerance=100
                        ),
                        description="Change data capture from the orders table.",
                    )
                )
                _logger.info(
                    "seed_source_created", name=source_view.name, id=source_view.id
                )
            except ConflictError:
                _logger.info("seed_source_skipped", name="orders-postgres-cdc")

            try:
                job_view = await processing_service.define_job(
                    DefineJobCommand(
                        name="orders-enrichment",
                        source=EndpointInput(kind="kafka_topic", resource="cdc.public.orders"),
                        sink=EndpointInput(kind="iceberg", resource="silver.orders_enriched"),
                        delivery_guarantee="exactly_once",
                        checkpoint=CheckpointInput(interval_ms=30_000),
                        parallelism=2,
                        contract_id=orders_contract_id,
                        description="Enrich order events and land them in the silver lakehouse layer.",
                    )
                )
                _logger.info("seed_job_created", name=job_view.name, id=job_view.id)
            except ConflictError:
                _logger.info("seed_job_skipped", name="orders-enrichment")
    finally:
        await engine.dispose()


async def _resolve_contract_id(
    contract_service: DataContractApplicationService, name: str
) -> str | None:
    page = await contract_service.list_contracts(ListContractsQuery(page=1, size=100))
    for item in page.items:
        if item.name == name:
            return item.id
    return None


if __name__ == "__main__":
    asyncio.run(_seed())
