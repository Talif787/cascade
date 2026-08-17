from __future__ import annotations

from dataclasses import dataclass

from cascade.domain.common.events import DomainEvent
from cascade.domain.processing.value_objects import JobStatus, StreamJobId


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamJobEvent(DomainEvent):
    job_id: StreamJobId


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamJobDefined(StreamJobEvent):
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class JobSubmitted(StreamJobEvent):
    runtime_ref: str


@dataclass(frozen=True, slots=True, kw_only=True)
class JobStatusChanged(StreamJobEvent):
    previous: JobStatus
    current: JobStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class SavepointTriggered(StreamJobEvent):
    location: str


@dataclass(frozen=True, slots=True, kw_only=True)
class JobRestarted(StreamJobEvent):
    reason: str
