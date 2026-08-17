from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from cascade.domain.contracts.aggregate import DataContract
from cascade.domain.contracts.value_objects import ContractName, ContractStatus, DataContractId


class ContractSortField(StrEnum):
    NAME = "name"
    STATUS = "status"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(frozen=True, slots=True)
class DataContractQuery:
    status: ContractStatus | None = None
    offset: int = 0
    limit: int = 20
    sort_by: ContractSortField = ContractSortField.CREATED_AT
    descending: bool = True


class DataContractRepository(ABC):
    @abstractmethod
    async def add(self, contract: DataContract) -> None: ...

    @abstractmethod
    async def update(self, contract: DataContract) -> None: ...

    @abstractmethod
    async def get(self, contract_id: DataContractId) -> DataContract | None: ...

    @abstractmethod
    async def get_by_name(self, name: ContractName) -> DataContract | None: ...

    @abstractmethod
    async def exists_by_name(self, name: ContractName) -> bool: ...

    @abstractmethod
    async def list(self, query: DataContractQuery) -> tuple[list[DataContract], int]: ...
