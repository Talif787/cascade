from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import FastAPI, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from cascade.application.common.unit_of_work import UnitOfWorkFactory
from cascade.application.contracts.registry import SchemaRegistry
from cascade.application.ingestion.runtime import ConnectorRuntime
from cascade.infrastructure.cache.base import Cache
from cascade.infrastructure.config import Settings
from cascade.infrastructure.logging import configure_logging
from cascade.infrastructure.metrics import render_metrics
from cascade.infrastructure.security.jwt import TokenVerifier
from cascade.infrastructure.telemetry import configure_tracing, instrument_app
from cascade.presentation.api.errors import register_exception_handlers
from cascade.presentation.api.middleware.correlation import CorrelationIdMiddleware
from cascade.presentation.api.middleware.logging import AccessLogMiddleware
from cascade.presentation.api.middleware.rate_limit import RateLimitMiddleware
from cascade.presentation.api.routers import contracts, health, ingestion, pipelines

HealthCheck = Callable[[], Awaitable[bool]]

_logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class AppComponents:
    uow_factory: UnitOfWorkFactory
    cache: Cache
    token_verifier: TokenVerifier
    schema_registry: SchemaRegistry
    connector_runtime: ConnectorRuntime
    health_checks: dict[str, HealthCheck] = field(default_factory=dict)
    engine: AsyncEngine | None = None
    redis: Any | None = None


def create_app(settings: Settings, components: AppComponents | None = None) -> FastAPI:
    configure_logging(settings)
    configure_tracing(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = components or _build_components(settings)
        app.state.settings = settings
        app.state.uow_factory = resolved.uow_factory
        app.state.cache = resolved.cache
        app.state.token_verifier = resolved.token_verifier
        app.state.schema_registry = resolved.schema_registry
        app.state.connector_runtime = resolved.connector_runtime
        app.state.health_checks = resolved.health_checks
        instrument_app(app, resolved.engine, settings)
        _logger.info("application_started", environment=settings.environment.value)
        try:
            yield
        finally:
            if components is None:
                await _shutdown(resolved)

    app = FastAPI(
        title="Cascade Control Plane",
        version="0.1.0",
        description="Governance API for the Cascade real-time streaming data platform.",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        root_path=settings.root_path,
        lifespan=lifespan,
    )
    app.state.settings = settings

    register_exception_handlers(app)

    if settings.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            rate_per_second=settings.rate_limit_per_minute / 60.0,
            burst=settings.rate_limit_burst,
        )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    app.include_router(health.router)
    app.include_router(pipelines.router)
    app.include_router(contracts.router)
    app.include_router(ingestion.router)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    return app


def _build_components(settings: Settings) -> AppComponents:
    from redis.asyncio import Redis

    from cascade.infrastructure.cache.redis_cache import RedisCache
    from cascade.infrastructure.connect.factory import build_connector_runtime
    from cascade.infrastructure.database.engine import create_engine, create_session_factory
    from cascade.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
    from cascade.infrastructure.registry.factory import build_schema_registry
    from cascade.infrastructure.security.jwt import build_verifier

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    cache = RedisCache(redis)

    async def _check_database() -> bool:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True

    async def _check_redis() -> bool:
        return await cache.ping()

    return AppComponents(
        uow_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
        cache=cache,
        token_verifier=build_verifier(settings),
        schema_registry=build_schema_registry(settings),
        connector_runtime=build_connector_runtime(settings),
        health_checks={"database": _check_database, "redis": _check_redis},
        engine=engine,
        redis=redis,
    )


async def _shutdown(components: AppComponents) -> None:
    if components.engine is not None:
        await components.engine.dispose()
    if components.redis is not None:
        await components.redis.aclose()
    _logger.info("application_stopped")
