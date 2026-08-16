from __future__ import annotations

from dataclasses import dataclass

from cascade.domain.common.events import DomainEvent
from cascade.domain.pipelines.value_objects import PipelineId, PipelineStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineEvent(DomainEvent):
    pipeline_id: PipelineId


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineRegistered(PipelineEvent):
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineStatusChanged(PipelineEvent):
    previous: PipelineStatus
    current: PipelineStatus
