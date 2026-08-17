from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.processing.aggregate import StreamJob
from cascade.domain.processing.value_objects import (
    DeliveryGuarantee,
    JobName,
    JobStatus,
    SinkKind,
    StreamJobId,
)


class JobSortField(StrEnum):
    NAME = "name"
    STATUS = "status"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(frozen=True, slots=True)
class StreamJobQuery:
    status: JobStatus | None = None
    sink_kind: SinkKind | None = None
    delivery_guarantee: DeliveryGuarantee | None = None
    contract_id: DataContractId | None = None
    offset: int = 0
    limit: int = 20
    sort_by: JobSortField = JobSortField.CREATED_AT
    descending: bool = True


class StreamJobRepository(ABC):
    @abstractmethod
    async def add(self, job: StreamJob) -> None: ...

    @abstractmethod
    async def update(self, job: StreamJob) -> None: ...

    @abstractmethod
    async def get(self, job_id: StreamJobId) -> StreamJob | None: ...

    @abstractmethod
    async def get_by_name(self, name: JobName) -> StreamJob | None: ...

    @abstractmethod
    async def exists_by_name(self, name: JobName) -> bool: ...

    @abstractmethod
    async def list(self, query: StreamJobQuery) -> tuple[list[StreamJob], int]: ...
