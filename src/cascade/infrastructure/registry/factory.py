from __future__ import annotations

from cascade.application.contracts.registry import SchemaRegistry
from cascade.infrastructure.config import Settings
from cascade.infrastructure.registry.confluent import ConfluentSchemaRegistry
from cascade.infrastructure.registry.in_memory import InMemorySchemaRegistry


def build_schema_registry(settings: Settings) -> SchemaRegistry:
    if settings.schema_registry_url:
        return ConfluentSchemaRegistry(settings.schema_registry_url)
    return InMemorySchemaRegistry()
