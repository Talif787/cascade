from __future__ import annotations

from cascade.application.processing.runtime import JobSpec
from cascade.domain.processing.value_objects import (
    DeliveryGuarantee,
    RestartKind,
    SinkKind,
)

_CHECKPOINTING_MODE = {
    DeliveryGuarantee.EXACTLY_ONCE: "EXACTLY_ONCE",
    DeliveryGuarantee.AT_LEAST_ONCE: "AT_LEAST_ONCE",
}

_ICEBERG_CONNECTOR = "iceberg"
_RESTART_STRATEGY = {
    RestartKind.NONE: "none",
    RestartKind.FIXED_DELAY: "fixed-delay",
    RestartKind.EXPONENTIAL_DELAY: "exponential-delay",
    RestartKind.FAILURE_RATE: "failure-rate",
}


def build_job_config(spec: JobSpec) -> dict[str, str]:
    """Produce the Flink pipeline configuration for a job.

    The Iceberg sink commits are coordinated with checkpoints, so exactly-once
    delivery is expressed by enabling checkpointing in EXACTLY_ONCE mode.
    """

    checkpoint = spec.checkpoint_config
    config: dict[str, str] = {
        "pipeline.name": spec.name,
        "parallelism.default": str(spec.parallelism),
        "execution.checkpointing.interval": f"{checkpoint.interval_ms}ms",
        "execution.checkpointing.mode": _CHECKPOINTING_MODE[spec.delivery_guarantee],
        "execution.checkpointing.timeout": f"{checkpoint.timeout_ms}ms",
        "execution.checkpointing.min-pause": f"{checkpoint.min_pause_ms}ms",
        "execution.checkpointing.max-concurrent-checkpoints": str(checkpoint.max_concurrent),
        "restart-strategy.type": _RESTART_STRATEGY[spec.restart_strategy.kind],
    }
    if spec.restart_strategy.kind is RestartKind.FIXED_DELAY:
        config["restart-strategy.fixed-delay.attempts"] = str(spec.restart_strategy.attempts)
        config["restart-strategy.fixed-delay.delay"] = f"{spec.restart_strategy.delay_ms}ms"
    if spec.sink.kind is SinkKind.ICEBERG:
        config["sink.connector"] = _ICEBERG_CONNECTOR
        config["sink.table"] = spec.sink.resource
        config["sink.upsert-enabled"] = "false"
    if spec.savepoint_location is not None:
        config["execution.savepoint.path"] = spec.savepoint_location
    return config
