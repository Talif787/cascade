from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import AggregateRoot, utcnow
from cascade.domain.pipelines.errors import InvalidStateTransition
from cascade.domain.pipelines.events import PipelineRegistered, PipelineStatusChanged
from cascade.domain.pipelines.value_objects import (
    PipelineId,
    PipelineName,
    PipelineStatus,
    SinkTarget,
    SourceConnector,
)

_MAX_DESCRIPTION_LEN = 1024

_ALLOWED_TRANSITIONS: dict[PipelineStatus, frozenset[PipelineStatus]] = {
    PipelineStatus.DRAFT: frozenset({PipelineStatus.ACTIVE, PipelineStatus.ARCHIVED}),
    PipelineStatus.ACTIVE: frozenset({PipelineStatus.PAUSED, PipelineStatus.ARCHIVED}),
    PipelineStatus.PAUSED: frozenset({PipelineStatus.ACTIVE, PipelineStatus.ARCHIVED}),
    PipelineStatus.ARCHIVED: frozenset(),
}


class Pipeline(AggregateRoot[PipelineId]):
    """A managed movement of data from a source to a sink."""

    def __init__(
        self,
        pipeline_id: PipelineId,
        *,
        name: PipelineName,
        source: SourceConnector,
        sink: SinkTarget,
        status: PipelineStatus,
        description: str,
        created_at: datetime,
        updated_at: datetime,
        version: int = 0,
    ) -> None:
        super().__init__(pipeline_id, version=version)
        self._name = name
        self._source = source
        self._sink = sink
        self._status = status
        self._description = description
        self._created_at = created_at
        self._updated_at = updated_at

    @classmethod
    def register(
        cls,
        *,
        name: PipelineName,
        source: SourceConnector,
        sink: SinkTarget,
        description: str = "",
    ) -> Pipeline:
        now = utcnow()
        pipeline = cls(
            PipelineId.new(),
            name=name,
            source=source,
            sink=sink,
            status=PipelineStatus.DRAFT,
            description=_clamp_description(description),
            created_at=now,
            updated_at=now,
        )
        pipeline._record(PipelineRegistered(pipeline_id=pipeline.id, name=str(name)))
        return pipeline

    @property
    def name(self) -> PipelineName:
        return self._name

    @property
    def source(self) -> SourceConnector:
        return self._source

    @property
    def sink(self) -> SinkTarget:
        return self._sink

    @property
    def status(self) -> PipelineStatus:
        return self._status

    @property
    def description(self) -> str:
        return self._description

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def activate(self) -> None:
        self._transition_to(PipelineStatus.ACTIVE)

    def pause(self) -> None:
        self._transition_to(PipelineStatus.PAUSED)

    def archive(self) -> None:
        self._transition_to(PipelineStatus.ARCHIVED)

    def _transition_to(self, target: PipelineStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self._status]:
            raise InvalidStateTransition(self._status.value, target.value)
        previous = self._status
        self._status = target
        self._updated_at = utcnow()
        self._record(PipelineStatusChanged(pipeline_id=self.id, previous=previous, current=target))


def _clamp_description(description: str) -> str:
    return description.strip()[:_MAX_DESCRIPTION_LEN]
