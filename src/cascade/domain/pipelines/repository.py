from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from cascade.domain.pipelines.aggregate import Pipeline
from cascade.domain.pipelines.value_objects import PipelineId, PipelineName, PipelineStatus


class PipelineSortField(StrEnum):
    NAME = "name"
    STATUS = "status"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(frozen=True, slots=True)
class PipelineQuery:
    status: PipelineStatus | None = None
    offset: int = 0
    limit: int = 20
    sort_by: PipelineSortField = PipelineSortField.CREATED_AT
    descending: bool = True


class PipelineRepository(ABC):
    """Persistence port for the Pipeline aggregate."""

    @abstractmethod
    async def add(self, pipeline: Pipeline) -> None: ...

    @abstractmethod
    async def update(self, pipeline: Pipeline) -> None: ...

    @abstractmethod
    async def get(self, pipeline_id: PipelineId) -> Pipeline | None: ...

    @abstractmethod
    async def get_by_name(self, name: PipelineName) -> Pipeline | None: ...

    @abstractmethod
    async def exists_by_name(self, name: PipelineName) -> bool: ...

    @abstractmethod
    async def list(self, query: PipelineQuery) -> tuple[list[Pipeline], int]: ...
