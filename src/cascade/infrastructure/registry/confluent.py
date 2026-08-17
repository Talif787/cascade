from __future__ import annotations

import httpx

from cascade.application.contracts.registry import RegistrationResult, SchemaRegistry
from cascade.domain.contracts.value_objects import SchemaDefinition, SchemaFormat
from cascade.infrastructure.registry.serialization import to_avro_json

_FORMAT_HEADER = {
    SchemaFormat.AVRO: "AVRO",
    SchemaFormat.PROTOBUF: "PROTOBUF",
    SchemaFormat.JSON_SCHEMA: "JSON",
}


class SchemaRegistryError(RuntimeError):
    """Raised when the external schema registry rejects a request."""


class ConfluentSchemaRegistry(SchemaRegistry):
    """Adapter for a Confluent-compatible schema registry REST API."""

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def register(
        self, subject: str, schema: SchemaDefinition, schema_format: SchemaFormat
    ) -> RegistrationResult:
        payload = {
            "schema": to_avro_json(subject, schema),
            "schemaType": _FORMAT_HEADER[schema_format],
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/subjects/{subject}/versions",
                json=payload,
                headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
            )
        if response.status_code >= 400:
            raise SchemaRegistryError(
                f"registry rejected subject {subject!r}: {response.status_code} {response.text}"
            )
        registry_id = int(response.json()["id"])
        return RegistrationResult(registry_id=registry_id, subject=subject, version=0)

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/subjects")
            return response.status_code < 500
        except httpx.HTTPError:
            return False
