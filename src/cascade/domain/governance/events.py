from __future__ import annotations

from dataclasses import dataclass

from cascade.domain.common.events import DomainEvent
from cascade.domain.governance.value_objects import (
    ComplianceState,
    CostEntryId,
    SloId,
    SloStatus,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SloEvent(DomainEvent):
    slo_id: SloId


@dataclass(frozen=True, slots=True, kw_only=True)
class SloRegistered(SloEvent):
    name: str
    asset: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FreshnessEvaluated(SloEvent):
    state: ComplianceState
    staleness_minutes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SloBreached(SloEvent):
    staleness_minutes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SloStatusChanged(SloEvent):
    previous: SloStatus
    current: SloStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class FreshnessTargetChanged(SloEvent):
    max_staleness_minutes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CostRecorded(DomainEvent):
    cost_entry_id: CostEntryId
    asset: str
    amount_cents: int
