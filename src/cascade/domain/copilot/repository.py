from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from cascade.domain.copilot.aggregate import CopilotQuery
from cascade.domain.copilot.value_objects import CopilotQueryId, CopilotStatus


class CopilotQuerySortField(StrEnum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(frozen=True, slots=True)
class CopilotQueryFilter:
    status: CopilotStatus | None = None
    view_id: str | None = None
    offset: int = 0
    limit: int = 20
    sort_by: CopilotQuerySortField = CopilotQuerySortField.CREATED_AT
    descending: bool = True


class CopilotQueryRepository(ABC):
    @abstractmethod
    async def add(self, query: CopilotQuery) -> None: ...

    @abstractmethod
    async def update(self, query: CopilotQuery) -> None: ...

    @abstractmethod
    async def get(self, query_id: CopilotQueryId) -> CopilotQuery | None: ...

    @abstractmethod
    async def list(self, query_filter: CopilotQueryFilter) -> tuple[list[CopilotQuery], int]: ...

    @abstractmethod
    async def recent(self, limit: int) -> Sequence[CopilotQuery]: ...
