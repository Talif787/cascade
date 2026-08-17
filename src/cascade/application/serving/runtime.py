from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from cascade.domain.serving.value_objects import (
    ClickHouseEngine,
    Column,
    FilterClause,
    MeasureSelection,
)


class ClickHouseRuntimeError(RuntimeError):
    """Raised when the ClickHouse runtime cannot satisfy a request."""


@dataclass(frozen=True, slots=True)
class ServingTableSpec:
    name: str
    engine: ClickHouseEngine
    columns: tuple[Column, ...]
    order_by: tuple[str, ...]
    partition_by: str | None
    source_table: str


@dataclass(frozen=True, slots=True)
class SyncResult:
    sync_ref: str
    row_count: int


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    table: str
    dimensions: tuple[str, ...]
    measures: tuple[MeasureSelection, ...]
    filters: tuple[FilterClause, ...]
    limit: int


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...] = field(default_factory=tuple)


class ClickHouseRuntime(ABC):
    """Port for the ClickHouse cluster that serves curated data."""

    @abstractmethod
    async def create_or_replace(self, spec: ServingTableSpec) -> None: ...

    @abstractmethod
    async def sync(self, spec: ServingTableSpec) -> SyncResult: ...

    @abstractmethod
    async def drop(self, name: str) -> None: ...

    @abstractmethod
    async def query(self, compiled: CompiledQuery) -> QueryResult: ...
