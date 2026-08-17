from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import utcnow
from cascade.domain.contracts.value_objects import (
    SchemaDefinition,
    VersionStatus,
)


class SchemaVersion:
    """A single published schema revision belonging to a data contract."""

    def __init__(
        self,
        *,
        version: int,
        schema: SchemaDefinition,
        status: VersionStatus,
        created_at: datetime,
        registry_id: int | None = None,
    ) -> None:
        self._version = version
        self._schema = schema
        self._status = status
        self._created_at = created_at
        self._registry_id = registry_id

    @classmethod
    def create(cls, version: int, schema: SchemaDefinition) -> SchemaVersion:
        return cls(
            version=version,
            schema=schema,
            status=VersionStatus.PUBLISHED,
            created_at=utcnow(),
        )

    @property
    def version(self) -> int:
        return self._version

    @property
    def schema(self) -> SchemaDefinition:
        return self._schema

    @property
    def status(self) -> VersionStatus:
        return self._status

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def registry_id(self) -> int | None:
        return self._registry_id

    @property
    def is_published(self) -> bool:
        return self._status is VersionStatus.PUBLISHED

    def deprecate(self) -> None:
        self._status = VersionStatus.DEPRECATED

    def assign_registry_id(self, registry_id: int) -> None:
        self._registry_id = registry_id
