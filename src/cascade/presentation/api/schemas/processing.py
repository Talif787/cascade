from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cascade.application.processing.dto import JobView


class EndpointPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(examples=["kafka_topic"])
    resource: str = Field(min_length=1, max_length=512, examples=["events.orders"])


class CheckpointPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_ms: int = Field(default=60_000, gt=0)
    timeout_ms: int = Field(default=600_000, gt=0)
    min_pause_ms: int = Field(default=0, ge=0)
    max_concurrent: int = Field(default=1, ge=1)


class RestartPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="fixed_delay", examples=["fixed_delay"])
    attempts: int = Field(default=3, ge=0)
    delay_ms: int = Field(default=10_000, ge=0)


class DefineJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=63, examples=["orders-enrichment"])
    source: EndpointPayload
    sink: EndpointPayload
    delivery_guarantee: str = Field(default="exactly_once", examples=["exactly_once"])
    checkpoint: CheckpointPayload = Field(default_factory=CheckpointPayload)
    restart: RestartPayload = Field(default_factory=RestartPayload)
    parallelism: int = Field(default=1, ge=1, le=1024)
    contract_id: str | None = None
    description: str = Field(default="", max_length=1024)


class ChangeCheckpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checkpoint: CheckpointPayload


class EndpointResponse(BaseModel):
    kind: str
    resource: str


class CheckpointResponse(BaseModel):
    interval_ms: int
    timeout_ms: int
    min_pause_ms: int
    max_concurrent: int


class RestartResponse(BaseModel):
    kind: str
    attempts: int
    delay_ms: int


class JobResponse(BaseModel):
    id: str
    name: str
    source: EndpointResponse
    sink: EndpointResponse
    delivery_guarantee: str
    checkpoint_config: CheckpointResponse
    restart_strategy: RestartResponse
    parallelism: int
    contract_id: str | None
    status: str
    runtime_ref: str | None
    savepoint_location: str | None
    description: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_view(cls, view: JobView) -> JobResponse:
        return cls(
            id=view.id,
            name=view.name,
            source=EndpointResponse(kind=view.source.kind, resource=view.source.resource),
            sink=EndpointResponse(kind=view.sink.kind, resource=view.sink.resource),
            delivery_guarantee=view.delivery_guarantee,
            checkpoint_config=CheckpointResponse(
                interval_ms=view.checkpoint_config.interval_ms,
                timeout_ms=view.checkpoint_config.timeout_ms,
                min_pause_ms=view.checkpoint_config.min_pause_ms,
                max_concurrent=view.checkpoint_config.max_concurrent,
            ),
            restart_strategy=RestartResponse(
                kind=view.restart_strategy.kind,
                attempts=view.restart_strategy.attempts,
                delay_ms=view.restart_strategy.delay_ms,
            ),
            parallelism=view.parallelism,
            contract_id=view.contract_id,
            status=view.status,
            runtime_ref=view.runtime_ref,
            savepoint_location=view.savepoint_location,
            description=view.description,
            version=view.version,
            created_at=view.created_at,
            updated_at=view.updated_at,
        )
