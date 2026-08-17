from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.lakehouse.aggregate import Dataset
from cascade.domain.lakehouse.value_objects import (
    DatasetId,
    DatasetName,
    DatasetStatus,
    MedallionLayer,
    QualityStatus,
)


class DatasetSortField(StrEnum):
    NAME = "name"
    LAYER = "layer"
    STATUS = "status"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(frozen=True, slots=True)
class DatasetQuery:
    layer: MedallionLayer | None = None
    status: DatasetStatus | None = None
    quality_status: QualityStatus | None = None
    contract_id: DataContractId | None = None
    offset: int = 0
    limit: int = 20
    sort_by: DatasetSortField = DatasetSortField.CREATED_AT
    descending: bool = True


class DatasetRepository(ABC):
    @abstractmethod
    async def add(self, dataset: Dataset) -> None: ...

    @abstractmethod
    async def update(self, dataset: Dataset) -> None: ...

    @abstractmethod
    async def get(self, dataset_id: DatasetId) -> Dataset | None: ...

    @abstractmethod
    async def get_by_name(self, name: DatasetName) -> Dataset | None: ...

    @abstractmethod
    async def exists_by_name(self, name: DatasetName) -> bool: ...

    @abstractmethod
    async def list(self, query: DatasetQuery) -> tuple[list[Dataset], int]: ...

    @abstractmethod
    async def list_dependents(self, dataset_id: DatasetId) -> Sequence[Dataset]: ...
