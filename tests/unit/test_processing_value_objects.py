from __future__ import annotations

import pytest

from cascade.domain.processing.errors import (
    InvalidCheckpointConfig,
    InvalidJobEndpoint,
    InvalidJobId,
    InvalidJobName,
    InvalidRestartStrategy,
)
from cascade.domain.processing.value_objects import (
    CheckpointConfig,
    JobName,
    JobSink,
    JobSource,
    RestartStrategy,
    SinkKind,
    SourceKind,
    StreamJobId,
)


@pytest.mark.parametrize("value", ["orders-enrichment", "job1x", "a-b-c"])
def test_valid_job_names(value: str) -> None:
    assert str(JobName(value)) == value


@pytest.mark.parametrize("value", ["", "ab", "Orders", "1abc", "has space", "x" * 64])
def test_invalid_job_names(value: str) -> None:
    with pytest.raises(InvalidJobName):
        JobName(value)


def test_job_id_round_trip() -> None:
    identity = StreamJobId.new()
    assert StreamJobId.from_string(str(identity)) == identity


def test_job_id_rejects_non_uuid() -> None:
    with pytest.raises(InvalidJobId):
        StreamJobId.from_string("nope")


def test_iceberg_sink_flags_exactly_once_requirement() -> None:
    sink = JobSink(kind=SinkKind.ICEBERG, resource="lake.silver.orders")
    assert sink.requires_exactly_once is True


def test_kafka_sink_does_not_require_exactly_once() -> None:
    sink = JobSink(kind=SinkKind.KAFKA_TOPIC, resource="events.enriched")
    assert sink.requires_exactly_once is False


def test_empty_endpoint_resource_is_rejected() -> None:
    with pytest.raises(InvalidJobEndpoint):
        JobSource(kind=SourceKind.KAFKA_TOPIC, resource="  ")


def test_checkpoint_interval_must_be_positive() -> None:
    with pytest.raises(InvalidCheckpointConfig):
        CheckpointConfig(interval_ms=0)


def test_checkpoint_rejects_negative_pause() -> None:
    with pytest.raises(InvalidCheckpointConfig):
        CheckpointConfig(min_pause_ms=-1)


def test_checkpoint_requires_at_least_one_concurrent() -> None:
    with pytest.raises(InvalidCheckpointConfig):
        CheckpointConfig(max_concurrent=0)


def test_restart_strategy_rejects_negative_attempts() -> None:
    with pytest.raises(InvalidRestartStrategy):
        RestartStrategy(attempts=-1)
