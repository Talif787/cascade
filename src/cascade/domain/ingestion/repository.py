from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.ingestion.aggregate import IngestionSource
from cascade.domain.ingestion.value_objects import (
    ConnectorKind,
    IngestionSourceId,
    SourceName,
    SourceStatus,
)


class SourceSortField(StrEnum):
    NAME = "name"
    STATUS = "status"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(frozen=True, slots=True)
class IngestionSourceQuery:
    status: SourceStatus | None = None
    connector_kind: ConnectorKind | None = None
    contract_id: DataContractId | None = None
    offset: int = 0
    limit: int = 20
    sort_by: SourceSortField = SourceSortField.CREATED_AT
    descending: bool = True


class IngestionSourceRepository(ABC):
    @abstractmethod
    async def add(self, source: IngestionSource) -> None: ...

    @abstractmethod
    async def update(self, source: IngestionSource) -> None: ...

    @abstractmethod
    async def get(self, source_id: IngestionSourceId) -> IngestionSource | None: ...

    @abstractmethod
    async def get_by_name(self, name: SourceName) -> IngestionSource | None: ...

    @abstractmethod
    async def exists_by_name(self, name: SourceName) -> bool: ...

    @abstractmethod
    async def list(self, query: IngestionSourceQuery) -> tuple[list[IngestionSource], int]: ...
