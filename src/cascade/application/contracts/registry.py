from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from cascade.domain.contracts.value_objects import SchemaDefinition, SchemaFormat


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    registry_id: int
    subject: str
    version: int


class SchemaRegistry(ABC):
    """Port for an external schema registry (system of record for schemas)."""

    @abstractmethod
    async def register(
        self, subject: str, schema: SchemaDefinition, schema_format: SchemaFormat
    ) -> RegistrationResult: ...

    @abstractmethod
    async def ping(self) -> bool: ...
