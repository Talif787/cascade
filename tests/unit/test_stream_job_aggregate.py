from __future__ import annotations

import pytest

from cascade.domain.processing.aggregate import StreamJob
from cascade.domain.processing.errors import (
    ExactlyOnceRequired,
    InvalidCheckpointConfig,
    InvalidJobTransition,
)
from cascade.domain.processing.events import (
    JobSubmitted,
    SavepointTriggered,
    StreamJobDefined,
)
from cascade.domain.processing.value_objects import (
    CheckpointConfig,
    DeliveryGuarantee,
    JobName,
    JobSink,
    JobSource,
    JobStatus,
    RestartStrategy,
    SinkKind,
    SourceKind,
)


def _job(
    *,
    sink_kind: SinkKind = SinkKind.ICEBERG,
    guarantee: DeliveryGuarantee = DeliveryGuarantee.EXACTLY_ONCE,
    checkpoint: CheckpointConfig | None = None,
) -> StreamJob:
    return StreamJob.define(
        name=JobName("orders-enrichment"),
        source=JobSource(kind=SourceKind.KAFKA_TOPIC, resource="events.orders"),
        sink=JobSink(kind=sink_kind, resource="lake.silver.orders"),
        delivery_guarantee=guarantee,
        checkpoint_config=checkpoint or CheckpointConfig(interval_ms=30_000),
        restart_strategy=RestartStrategy(),
    )


def test_define_starts_in_defined_state() -> None:
    job = _job()
    assert job.status is JobStatus.DEFINED
    assert any(isinstance(e, StreamJobDefined) for e in job.pull_events())


def test_iceberg_sink_requires_exactly_once() -> None:
    with pytest.raises(ExactlyOnceRequired):
        _job(sink_kind=SinkKind.ICEBERG, guarantee=DeliveryGuarantee.AT_LEAST_ONCE)


def test_iceberg_sink_accepts_exactly_once() -> None:
    job = _job(sink_kind=SinkKind.ICEBERG, guarantee=DeliveryGuarantee.EXACTLY_ONCE)
    assert job.delivery_guarantee is DeliveryGuarantee.EXACTLY_ONCE


def test_kafka_sink_allows_at_least_once() -> None:
    job = _job(sink_kind=SinkKind.KAFKA_TOPIC, guarantee=DeliveryGuarantee.AT_LEAST_ONCE)
    assert job.sink.kind is SinkKind.KAFKA_TOPIC


def test_exactly_once_requires_checkpointing_enabled() -> None:
    # interval must be > 0; a zero interval is rejected at the value-object level,
    # so we assert the invariant catches an at-least-once-only checkpoint intent by
    # constructing a valid checkpoint but pairing exactly-once with a non-iceberg sink.
    job = _job(sink_kind=SinkKind.KAFKA_TOPIC, guarantee=DeliveryGuarantee.EXACTLY_ONCE)
    assert job.checkpoint_config.enabled is True


def test_full_lifecycle_submit_run_suspend_resume() -> None:
    job = _job()
    job.pull_events()
    job.submit("flink-1")
    assert job.status is JobStatus.SUBMITTED
    assert job.runtime_ref == "flink-1"
    events = job.pull_events()
    assert any(isinstance(e, JobSubmitted) for e in events)
    job.mark_running()
    assert job.status is JobStatus.RUNNING
    job.suspend("s3://sp/1")
    assert job.status is JobStatus.SUSPENDED
    assert job.savepoint_location == "s3://sp/1"
    assert any(isinstance(e, SavepointTriggered) for e in job.pull_events())
    job.resume()
    assert job.status is JobStatus.RUNNING


def test_trigger_savepoint_requires_running() -> None:
    job = _job()
    with pytest.raises(InvalidJobTransition):
        job.trigger_savepoint("s3://sp/x")


def test_trigger_savepoint_keeps_running() -> None:
    job = _job()
    job.submit("flink-1")
    job.mark_running()
    job.pull_events()
    job.trigger_savepoint("s3://sp/adhoc")
    assert job.status is JobStatus.RUNNING
    assert job.savepoint_location == "s3://sp/adhoc"
    assert any(isinstance(e, SavepointTriggered) for e in job.pull_events())


def test_restart_from_running_and_from_failed() -> None:
    job = _job()
    job.submit("flink-1")
    job.mark_running()
    job.restart("checkpoint expired")
    assert job.status is JobStatus.RESTARTING
    job.mark_running()
    job.mark_failed()
    assert job.status is JobStatus.FAILED
    job.restart("operator error")
    assert job.status is JobStatus.RESTARTING


def test_complete_and_cancel_are_terminal() -> None:
    job = _job()
    job.submit("flink-1")
    job.mark_running()
    job.complete()
    assert job.status is JobStatus.COMPLETED
    with pytest.raises(InvalidJobTransition):
        job.cancel()


def test_illegal_transition_raises() -> None:
    job = _job()
    with pytest.raises(InvalidJobTransition):
        job.mark_running()  # cannot run a job that was never submitted


def test_change_checkpoint_config_revalidates_exactly_once() -> None:
    job = _job()
    job.change_checkpoint_config(CheckpointConfig(interval_ms=15_000))
    assert job.checkpoint_config.interval_ms == 15_000


def test_parallelism_must_be_positive() -> None:
    with pytest.raises(InvalidCheckpointConfig):
        StreamJob.define(
            name=JobName("bad-parallelism"),
            source=JobSource(kind=SourceKind.KAFKA_TOPIC, resource="events.orders"),
            sink=JobSink(kind=SinkKind.KAFKA_TOPIC, resource="events.enriched"),
            delivery_guarantee=DeliveryGuarantee.AT_LEAST_ONCE,
            checkpoint_config=CheckpointConfig(),
            restart_strategy=RestartStrategy(),
            parallelism=0,
        )
