from __future__ import annotations

from dataclasses import dataclass

from cascade.domain.common.events import DomainEvent
from cascade.domain.contracts.value_objects import CompatibilityMode, DataContractId


@dataclass(frozen=True, slots=True, kw_only=True)
class ContractEvent(DomainEvent):
    contract_id: DataContractId


@dataclass(frozen=True, slots=True, kw_only=True)
class DataContractRegistered(ContractEvent):
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SchemaVersionPublished(ContractEvent):
    version: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CompatibilityModeChanged(ContractEvent):
    previous: CompatibilityMode
    current: CompatibilityMode


@dataclass(frozen=True, slots=True, kw_only=True)
class SchemaVersionDeprecated(ContractEvent):
    version: int


@dataclass(frozen=True, slots=True, kw_only=True)
class DataContractDeprecated(ContractEvent):
    pass
