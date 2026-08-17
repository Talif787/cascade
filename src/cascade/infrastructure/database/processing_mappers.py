from __future__ import annotations

from typing import Any

from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.processing.aggregate import StreamJob
from cascade.domain.processing.value_objects import (
    CheckpointConfig,
    DeliveryGuarantee,
    JobName,
    JobSink,
    JobSource,
    JobStatus,
    RestartKind,
    RestartStrategy,
    SinkKind,
    SourceKind,
    StreamJobId,
)
from cascade.infrastructure.database.models import StreamJobModel


def _source_to_dict(source: JobSource) -> dict[str, Any]:
    return {"kind": source.kind.value, "resource": source.resource}


def _sink_to_dict(sink: JobSink) -> dict[str, Any]:
    return {"kind": sink.kind.value, "resource": sink.resource}


def checkpoint_to_dict(config: CheckpointConfig) -> dict[str, Any]:
    return {
        "interval_ms": config.interval_ms,
        "timeout_ms": config.timeout_ms,
        "min_pause_ms": config.min_pause_ms,
        "max_concurrent": config.max_concurrent,
    }


def _restart_to_dict(strategy: RestartStrategy) -> dict[str, Any]:
    return {
        "kind": strategy.kind.value,
        "attempts": strategy.attempts,
        "delay_ms": strategy.delay_ms,
    }


def checkpoint_from_dict(payload: dict[str, Any]) -> CheckpointConfig:
    return CheckpointConfig(
        interval_ms=payload["interval_ms"],
        timeout_ms=payload["timeout_ms"],
        min_pause_ms=payload["min_pause_ms"],
        max_concurrent=payload["max_concurrent"],
    )


def job_to_model(job: StreamJob) -> StreamJobModel:
    return StreamJobModel(
        id=job.id.value,
        name=str(job.name),
        source=_source_to_dict(job.source),
        sink=_sink_to_dict(job.sink),
        delivery_guarantee=job.delivery_guarantee.value,
        checkpoint_config=checkpoint_to_dict(job.checkpoint_config),
        restart_strategy=_restart_to_dict(job.restart_strategy),
        parallelism=job.parallelism,
        contract_id=job.contract_id.value if job.contract_id is not None else None,
        status=job.status.value,
        runtime_ref=job.runtime_ref,
        savepoint_location=job.savepoint_location,
        description=job.description,
        version=job.version,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def model_to_job(model: StreamJobModel) -> StreamJob:
    return StreamJob(
        StreamJobId(model.id),
        name=JobName(model.name),
        source=JobSource(kind=SourceKind(model.source["kind"]), resource=model.source["resource"]),
        sink=JobSink(kind=SinkKind(model.sink["kind"]), resource=model.sink["resource"]),
        delivery_guarantee=DeliveryGuarantee(model.delivery_guarantee),
        checkpoint_config=checkpoint_from_dict(model.checkpoint_config),
        restart_strategy=RestartStrategy(
            kind=RestartKind(model.restart_strategy["kind"]),
            attempts=model.restart_strategy["attempts"],
            delay_ms=model.restart_strategy["delay_ms"],
        ),
        parallelism=model.parallelism,
        contract_id=DataContractId(model.contract_id) if model.contract_id is not None else None,
        status=JobStatus(model.status),
        runtime_ref=model.runtime_ref,
        savepoint_location=model.savepoint_location,
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )
