from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from cascade.domain.lakehouse.value_objects import DatasetId
from cascade.domain.serving.aggregate import ServingView
from cascade.domain.serving.value_objects import (
    ClickHouseEngine,
    ServingStatus,
    ServingViewId,
    ServingViewName,
)


class ServingViewSortField(StrEnum):
    NAME = "name"
    STATUS = "status"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(frozen=True, slots=True)
class ServingViewQuery:
    status: ServingStatus | None = None
    engine: ClickHouseEngine | None = None
    source_dataset_id: DatasetId | None = None
    offset: int = 0
    limit: int = 20
    sort_by: ServingViewSortField = ServingViewSortField.CREATED_AT
    descending: bool = True


class ServingViewRepository(ABC):
    @abstractmethod
    async def add(self, view: ServingView) -> None: ...

    @abstractmethod
    async def update(self, view: ServingView) -> None: ...

    @abstractmethod
    async def get(self, view_id: ServingViewId) -> ServingView | None: ...

    @abstractmethod
    async def get_by_name(self, name: ServingViewName) -> ServingView | None: ...

    @abstractmethod
    async def exists_by_name(self, name: ServingViewName) -> bool: ...

    @abstractmethod
    async def list(self, query: ServingViewQuery) -> tuple[list[ServingView], int]: ...

    @abstractmethod
    async def list_ready(self) -> Sequence[ServingView]: ...
