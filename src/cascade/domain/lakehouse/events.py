from __future__ import annotations

from dataclasses import dataclass

from cascade.domain.common.events import DomainEvent
from cascade.domain.lakehouse.value_objects import DatasetId, DatasetStatus, QualityStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class DatasetEvent(DomainEvent):
    dataset_id: DatasetId


@dataclass(frozen=True, slots=True, kw_only=True)
class DatasetRegistered(DatasetEvent):
    name: str
    layer: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializationStarted(DatasetEvent):
    run_ref: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DatasetMaterialized(DatasetEvent):
    run_ref: str
    row_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializationFailed(DatasetEvent):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class QualityEvaluated(DatasetEvent):
    status: QualityStatus
    passed: int
    failed: int


@dataclass(frozen=True, slots=True, kw_only=True)
class DatasetStatusChanged(DatasetEvent):
    previous: DatasetStatus
    current: DatasetStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduleChanged(DatasetEvent):
    enabled: bool
