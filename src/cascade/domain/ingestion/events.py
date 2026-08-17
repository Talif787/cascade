from __future__ import annotations

from dataclasses import dataclass

from cascade.domain.common.events import DomainEvent
from cascade.domain.ingestion.value_objects import IngestionSourceId, SourceStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class IngestionSourceEvent(DomainEvent):
    source_id: IngestionSourceId


@dataclass(frozen=True, slots=True, kw_only=True)
class IngestionSourceRegistered(IngestionSourceEvent):
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceProvisioned(IngestionSourceEvent):
    runtime_ref: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceStatusChanged(IngestionSourceEvent):
    previous: SourceStatus
    current: SourceStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class DeadLettersRecorded(IngestionSourceEvent):
    added: int
    total: int


@dataclass(frozen=True, slots=True, kw_only=True)
class DeadLetterThresholdBreached(IngestionSourceEvent):
    total: int
    tolerance: int
