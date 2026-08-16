from __future__ import annotations

from typing import Any

from cascade.domain.pipelines.aggregate import Pipeline
from cascade.domain.pipelines.value_objects import (
    ConnectorType,
    PipelineId,
    PipelineName,
    PipelineStatus,
    SinkTarget,
    SinkType,
    SourceConnector,
)
from cascade.infrastructure.database.models import PipelineModel


def source_to_dict(source: SourceConnector) -> dict[str, Any]:
    return {"type": source.type.value, "resource": source.resource, "options": dict(source.options)}


def sink_to_dict(sink: SinkTarget) -> dict[str, Any]:
    return {"type": sink.type.value, "resource": sink.resource, "options": dict(sink.options)}


def pipeline_to_model(pipeline: Pipeline) -> PipelineModel:
    return PipelineModel(
        id=pipeline.id.value,
        name=str(pipeline.name),
        source=source_to_dict(pipeline.source),
        sink=sink_to_dict(pipeline.sink),
        status=pipeline.status.value,
        description=pipeline.description,
        version=pipeline.version,
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
    )


def model_to_pipeline(model: PipelineModel) -> Pipeline:
    source = SourceConnector(
        type=ConnectorType(model.source["type"]),
        resource=model.source["resource"],
        options=model.source.get("options", {}),
    )
    sink = SinkTarget(
        type=SinkType(model.sink["type"]),
        resource=model.sink["resource"],
        options=model.sink.get("options", {}),
    )
    return Pipeline(
        PipelineId(model.id),
        name=PipelineName(model.name),
        source=source,
        sink=sink,
        status=PipelineStatus(model.status),
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )
