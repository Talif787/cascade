from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cascade.application.ingestion.dto import SourceView


class DeadLetterPolicyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on_failure: str = Field(default="dead_letter", examples=["dead_letter"])
    dlq_topic: str | None = Field(default=None, examples=["orders.dlq"])
    max_retries: int = Field(default=3, ge=0)
    tolerance: int = Field(default=0, ge=0)


class RegisterSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=63, examples=["orders-postgres-cdc"])
    connector_kind: str = Field(examples=["postgres_cdc"])
    config: dict[str, str] = Field(default_factory=dict)
    contract_id: str = Field(examples=["9b3c9215-e635-4d07-a379-ca21864ebddb"])
    pipeline_id: str | None = None
    dead_letter: DeadLetterPolicyPayload = Field(default_factory=DeadLetterPolicyPayload)
    description: str = Field(default="", max_length=1024)


class RecordDeadLettersRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0, examples=[5])


class ChangeDeadLetterPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dead_letter: DeadLetterPolicyPayload


class DeadLetterPolicyResponse(BaseModel):
    on_failure: str
    dlq_topic: str | None
    max_retries: int
    tolerance: int


class SourceResponse(BaseModel):
    id: str
    name: str
    connector_kind: str
    config: dict[str, str]
    contract_id: str
    pipeline_id: str | None
    status: str
    dead_letter_policy: DeadLetterPolicyResponse
    dead_letter_count: int
    runtime_ref: str | None
    description: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_view(cls, view: SourceView) -> SourceResponse:
        return cls(
            id=view.id,
            name=view.name,
            connector_kind=view.connector_kind,
            config=view.config,
            contract_id=view.contract_id,
            pipeline_id=view.pipeline_id,
            status=view.status,
            dead_letter_policy=DeadLetterPolicyResponse(
                on_failure=view.dead_letter_policy.on_failure,
                dlq_topic=view.dead_letter_policy.dlq_topic,
                max_retries=view.dead_letter_policy.max_retries,
                tolerance=view.dead_letter_policy.tolerance,
            ),
            dead_letter_count=view.dead_letter_count,
            runtime_ref=view.runtime_ref,
            description=view.description,
            version=view.version,
            created_at=view.created_at,
            updated_at=view.updated_at,
        )
