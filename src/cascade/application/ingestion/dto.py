from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cascade.domain.ingestion.aggregate import IngestionSource
from cascade.domain.ingestion.value_objects import DeadLetterPolicy


@dataclass(frozen=True, slots=True)
class DeadLetterPolicyView:
    on_failure: str
    dlq_topic: str | None
    max_retries: int
    tolerance: int

    @classmethod
    def from_policy(cls, policy: DeadLetterPolicy) -> DeadLetterPolicyView:
        return cls(
            on_failure=policy.on_failure.value,
            dlq_topic=policy.dlq_topic,
            max_retries=policy.max_retries,
            tolerance=policy.tolerance,
        )


@dataclass(frozen=True, slots=True)
class SourceView:
    id: str
    name: str
    connector_kind: str
    config: dict[str, str]
    contract_id: str
    pipeline_id: str | None
    status: str
    dead_letter_policy: DeadLetterPolicyView
    dead_letter_count: int
    runtime_ref: str | None
    description: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_aggregate(cls, source: IngestionSource) -> SourceView:
        return cls(
            id=str(source.id),
            name=str(source.name),
            connector_kind=source.connector_kind.value,
            config=source.config.as_dict(),
            contract_id=str(source.contract_id),
            pipeline_id=str(source.pipeline_id) if source.pipeline_id is not None else None,
            status=source.status.value,
            dead_letter_policy=DeadLetterPolicyView.from_policy(source.dead_letter_policy),
            dead_letter_count=source.dead_letter_count,
            runtime_ref=source.runtime_ref,
            description=source.description,
            version=source.version,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )
