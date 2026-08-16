from __future__ import annotations

from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from cascade.infrastructure.config import Settings

_logger = structlog.get_logger(__name__)
_configured = False


def configure_tracing(settings: Settings) -> None:
    """Install a global tracer provider exporting spans over OTLP/HTTP."""

    global _configured
    if _configured or not settings.otel_enabled:
        return

    resource = Resource.create(
        {
            "service.name": settings.app_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.environment.value,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True
    _logger.info("tracing_configured", endpoint=settings.otel_exporter_otlp_endpoint)


def instrument_app(app: Any, engine: Any, settings: Settings) -> None:
    """Instrument FastAPI and SQLAlchemy when tracing is enabled."""

    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,livez,readyz,metrics")
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
