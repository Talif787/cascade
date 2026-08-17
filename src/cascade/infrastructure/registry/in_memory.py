from __future__ import annotations

from cascade.application.contracts.registry import RegistrationResult, SchemaRegistry
from cascade.domain.contracts.value_objects import SchemaDefinition, SchemaFormat
from cascade.infrastructure.registry.serialization import to_avro_json


class InMemorySchemaRegistry(SchemaRegistry):
    """A registry that assigns monotonic ids without an external service."""

    def __init__(self) -> None:
        self._by_schema: dict[tuple[str, str], RegistrationResult] = {}
        self._versions: dict[str, int] = {}
        self._next_id = 1

    async def register(
        self, subject: str, schema: SchemaDefinition, schema_format: SchemaFormat
    ) -> RegistrationResult:
        canonical = to_avro_json(subject, schema)
        key = (subject, canonical)
        existing = self._by_schema.get(key)
        if existing is not None:
            return existing
        version = self._versions.get(subject, 0) + 1
        self._versions[subject] = version
        result = RegistrationResult(registry_id=self._next_id, subject=subject, version=version)
        self._next_id += 1
        self._by_schema[key] = result
        return result

    async def ping(self) -> bool:
        return True
