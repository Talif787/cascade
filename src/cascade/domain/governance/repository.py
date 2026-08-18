from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from cascade.domain.governance.aggregate import ServiceLevelObjective
from cascade.domain.governance.aggregate_cost import CostEntry
from cascade.domain.governance.value_objects import (
    AssetKind,
    AssetRef,
    ComplianceState,
    CostEntryId,
    SloId,
    SloName,
    SloStatus,
)


class SloSortField(StrEnum):
    NAME = "name"
    STATUS = "status"
    STATE = "state"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(frozen=True, slots=True)
class SloQuery:
    asset_kind: AssetKind | None = None
    status: SloStatus | None = None
    state: ComplianceState | None = None
    offset: int = 0
    limit: int = 20
    sort_by: SloSortField = SloSortField.CREATED_AT
    descending: bool = True


class SloRepository(ABC):
    @abstractmethod
    async def add(self, slo: ServiceLevelObjective) -> None: ...

    @abstractmethod
    async def update(self, slo: ServiceLevelObjective) -> None: ...

    @abstractmethod
    async def get(self, slo_id: SloId) -> ServiceLevelObjective | None: ...

    @abstractmethod
    async def get_by_name(self, name: SloName) -> ServiceLevelObjective | None: ...

    @abstractmethod
    async def exists_by_name(self, name: SloName) -> bool: ...

    @abstractmethod
    async def list(self, query: SloQuery) -> tuple[list[ServiceLevelObjective], int]: ...

    @abstractmethod
    async def list_active(self) -> Sequence[ServiceLevelObjective]: ...


@dataclass(frozen=True, slots=True)
class CostSummaryLine:
    key: str
    amount_cents: int


@dataclass(frozen=True, slots=True)
class CostSummary:
    total_cents: int
    by_category: tuple[CostSummaryLine, ...] = field(default_factory=tuple)
    by_asset: tuple[CostSummaryLine, ...] = field(default_factory=tuple)


class CostEntryRepository(ABC):
    @abstractmethod
    async def add(self, entry: CostEntry) -> None: ...

    @abstractmethod
    async def get(self, entry_id: CostEntryId) -> CostEntry | None: ...

    @abstractmethod
    async def list_for_asset(self, asset: AssetRef) -> Sequence[CostEntry]: ...

    @abstractmethod
    async def summarize(
        self, window_start: datetime | None, window_end: datetime | None
    ) -> CostSummary: ...
