from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cascade.domain.processing.aggregate import StreamJob
from cascade.domain.processing.value_objects import (
    CheckpointConfig,
    JobSink,
    JobSource,
    RestartStrategy,
)


@dataclass(frozen=True, slots=True)
class EndpointView:
    kind: str
    resource: str


@dataclass(frozen=True, slots=True)
class CheckpointConfigView:
    interval_ms: int
    timeout_ms: int
    min_pause_ms: int
    max_concurrent: int

    @classmethod
    def from_config(cls, config: CheckpointConfig) -> CheckpointConfigView:
        return cls(
            interval_ms=config.interval_ms,
            timeout_ms=config.timeout_ms,
            min_pause_ms=config.min_pause_ms,
            max_concurrent=config.max_concurrent,
        )


@dataclass(frozen=True, slots=True)
class RestartStrategyView:
    kind: str
    attempts: int
    delay_ms: int

    @classmethod
    def from_strategy(cls, strategy: RestartStrategy) -> RestartStrategyView:
        return cls(kind=strategy.kind.value, attempts=strategy.attempts, delay_ms=strategy.delay_ms)


@dataclass(frozen=True, slots=True)
class JobView:
    id: str
    name: str
    source: EndpointView
    sink: EndpointView
    delivery_guarantee: str
    checkpoint_config: CheckpointConfigView
    restart_strategy: RestartStrategyView
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
    def from_aggregate(cls, job: StreamJob) -> JobView:
        return cls(
            id=str(job.id),
            name=str(job.name),
            source=_endpoint(job.source),
            sink=_endpoint(job.sink),
            delivery_guarantee=job.delivery_guarantee.value,
            checkpoint_config=CheckpointConfigView.from_config(job.checkpoint_config),
            restart_strategy=RestartStrategyView.from_strategy(job.restart_strategy),
            parallelism=job.parallelism,
            contract_id=str(job.contract_id) if job.contract_id is not None else None,
            status=job.status.value,
            runtime_ref=job.runtime_ref,
            savepoint_location=job.savepoint_location,
            description=job.description,
            version=job.version,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


def _endpoint(endpoint: JobSource | JobSink) -> EndpointView:
    return EndpointView(kind=endpoint.kind.value, resource=endpoint.resource)
