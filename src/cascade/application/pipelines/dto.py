from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cascade.domain.pipelines.aggregate import Pipeline


@dataclass(frozen=True, slots=True)
class ConnectorView:
    type: str
    resource: str
    options: dict[str, str]


@dataclass(frozen=True, slots=True)
class PipelineView:
    id: str
    name: str
    source: ConnectorView
    sink: ConnectorView
    status: str
    description: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_aggregate(cls, pipeline: Pipeline) -> PipelineView:
        return cls(
            id=str(pipeline.id),
            name=str(pipeline.name),
            source=ConnectorView(
                type=pipeline.source.type.value,
                resource=pipeline.source.resource,
                options=dict(pipeline.source.options),
            ),
            sink=ConnectorView(
                type=pipeline.sink.type.value,
                resource=pipeline.sink.resource,
                options=dict(pipeline.sink.options),
            ),
            status=pipeline.status.value,
            description=pipeline.description,
            version=pipeline.version,
            created_at=pipeline.created_at,
            updated_at=pipeline.updated_at,
        )
