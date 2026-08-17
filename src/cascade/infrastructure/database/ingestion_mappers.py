from __future__ import annotations

from typing import Any

from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.ingestion.aggregate import IngestionSource
from cascade.domain.ingestion.value_objects import (
    ConnectorConfig,
    ConnectorKind,
    DeadLetterPolicy,
    FailureAction,
    IngestionSourceId,
    SourceName,
    SourceStatus,
)
from cascade.domain.pipelines.value_objects import PipelineId
from cascade.infrastructure.database.models import IngestionSourceModel


def policy_to_dict(policy: DeadLetterPolicy) -> dict[str, Any]:
    return {
        "on_failure": policy.on_failure.value,
        "dlq_topic": policy.dlq_topic,
        "max_retries": policy.max_retries,
        "tolerance": policy.tolerance,
    }


def dict_to_policy(payload: dict[str, Any]) -> DeadLetterPolicy:
    return DeadLetterPolicy(
        on_failure=FailureAction(payload["on_failure"]),
        dlq_topic=payload.get("dlq_topic"),
        max_retries=payload.get("max_retries", 3),
        tolerance=payload.get("tolerance", 0),
    )


def source_to_model(source: IngestionSource) -> IngestionSourceModel:
    return IngestionSourceModel(
        id=source.id.value,
        name=str(source.name),
        connector_kind=source.connector_kind.value,
        config=source.config.as_dict(),
        contract_id=source.contract_id.value,
        pipeline_id=source.pipeline_id.value if source.pipeline_id is not None else None,
        status=source.status.value,
        dead_letter_policy=policy_to_dict(source.dead_letter_policy),
        dead_letter_count=source.dead_letter_count,
        runtime_ref=source.runtime_ref,
        description=source.description,
        version=source.version,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def model_to_source(model: IngestionSourceModel) -> IngestionSource:
    return IngestionSource(
        IngestionSourceId(model.id),
        name=SourceName(model.name),
        connector_kind=ConnectorKind(model.connector_kind),
        config=ConnectorConfig(options=dict(model.config)),
        contract_id=DataContractId(model.contract_id),
        pipeline_id=PipelineId(model.pipeline_id) if model.pipeline_id is not None else None,
        status=SourceStatus(model.status),
        dead_letter_policy=dict_to_policy(model.dead_letter_policy),
        dead_letter_count=model.dead_letter_count,
        runtime_ref=model.runtime_ref,
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )
