from __future__ import annotations

import asyncio

import structlog

from cascade.application.pipelines.commands import ConnectorInput, RegisterPipelineCommand
from cascade.application.pipelines.service import PipelineApplicationService
from cascade.application.common.errors import ConflictError
from cascade.infrastructure.config import get_settings
from cascade.infrastructure.database.engine import create_engine, create_session_factory
from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from cascade.infrastructure.logging import configure_logging

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


async def _seed() -> None:
    settings = get_settings()
    configure_logging(settings)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    service = PipelineApplicationService(lambda: SqlAlchemyUnitOfWork(session_factory))
    try:
        for command in _SEEDS:
            try:
                view = await service.register_pipeline(command)
                _logger.info("seed_created", name=view.name, id=view.id)
            except ConflictError:
                _logger.info("seed_skipped", name=command.name)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_seed())
