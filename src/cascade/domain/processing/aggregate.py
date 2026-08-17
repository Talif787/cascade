from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import AggregateRoot, utcnow
from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.processing.errors import (
    ExactlyOnceRequired,
    InvalidCheckpointConfig,
    InvalidJobTransition,
)
from cascade.domain.processing.events import (
    JobRestarted,
    JobStatusChanged,
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
    StreamJobId,
)

_MAX_DESCRIPTION_LEN = 1024
_MAX_PARALLELISM = 1024

_ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.DEFINED: frozenset({JobStatus.SUBMITTED, JobStatus.CANCELLED}),
    JobStatus.SUBMITTED: frozenset({JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.RESTARTING,
            JobStatus.SUSPENDED,
            JobStatus.FAILED,
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RESTARTING: frozenset({JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.SUSPENDED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.FAILED: frozenset({JobStatus.RESTARTING, JobStatus.CANCELLED}),
    JobStatus.COMPLETED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


def _assert_exactly_once(
    sink: JobSink, guarantee: DeliveryGuarantee, checkpoint: CheckpointConfig
) -> None:
    if sink.requires_exactly_once and guarantee is not DeliveryGuarantee.EXACTLY_ONCE:
        raise ExactlyOnceRequired(
            f"a {sink.kind.value} sink requires the exactly_once delivery guarantee"
        )
    if guarantee is DeliveryGuarantee.EXACTLY_ONCE and not checkpoint.enabled:
        raise InvalidCheckpointConfig("exactly_once delivery requires checkpointing to be enabled")


class StreamJob(AggregateRoot[StreamJobId]):
    """A Flink stream-processing job managed by the control plane."""

    def __init__(
        self,
        job_id: StreamJobId,
        *,
        name: JobName,
        source: JobSource,
        sink: JobSink,
        delivery_guarantee: DeliveryGuarantee,
        checkpoint_config: CheckpointConfig,
        restart_strategy: RestartStrategy,
        parallelism: int,
        contract_id: DataContractId | None,
        status: JobStatus,
        runtime_ref: str | None,
        savepoint_location: str | None,
        description: str,
        created_at: datetime,
        updated_at: datetime,
        version: int = 0,
    ) -> None:
        super().__init__(job_id, version=version)
        self._name = name
        self._source = source
        self._sink = sink
        self._delivery_guarantee = delivery_guarantee
        self._checkpoint_config = checkpoint_config
        self._restart_strategy = restart_strategy
        self._parallelism = parallelism
        self._contract_id = contract_id
        self._status = status
        self._runtime_ref = runtime_ref
        self._savepoint_location = savepoint_location
        self._description = description
        self._created_at = created_at
        self._updated_at = updated_at

    @classmethod
    def define(
        cls,
        *,
        name: JobName,
        source: JobSource,
        sink: JobSink,
        delivery_guarantee: DeliveryGuarantee,
        checkpoint_config: CheckpointConfig,
        restart_strategy: RestartStrategy,
        parallelism: int = 1,
        contract_id: DataContractId | None = None,
        description: str = "",
    ) -> StreamJob:
        _assert_exactly_once(sink, delivery_guarantee, checkpoint_config)
        if parallelism < 1 or parallelism > _MAX_PARALLELISM:
            raise InvalidCheckpointConfig(f"parallelism must be between 1 and {_MAX_PARALLELISM}")
        now = utcnow()
        job = cls(
            StreamJobId.new(),
            name=name,
            source=source,
            sink=sink,
            delivery_guarantee=delivery_guarantee,
            checkpoint_config=checkpoint_config,
            restart_strategy=restart_strategy,
            parallelism=parallelism,
            contract_id=contract_id,
            status=JobStatus.DEFINED,
            runtime_ref=None,
            savepoint_location=None,
            description=description.strip()[:_MAX_DESCRIPTION_LEN],
            created_at=now,
            updated_at=now,
        )
        job._record(StreamJobDefined(job_id=job.id, name=str(name)))
        return job

    @property
    def name(self) -> JobName:
        return self._name

    @property
    def source(self) -> JobSource:
        return self._source

    @property
    def sink(self) -> JobSink:
        return self._sink

    @property
    def delivery_guarantee(self) -> DeliveryGuarantee:
        return self._delivery_guarantee

    @property
    def checkpoint_config(self) -> CheckpointConfig:
        return self._checkpoint_config

    @property
    def restart_strategy(self) -> RestartStrategy:
        return self._restart_strategy

    @property
    def parallelism(self) -> int:
        return self._parallelism

    @property
    def contract_id(self) -> DataContractId | None:
        return self._contract_id

    @property
    def status(self) -> JobStatus:
        return self._status

    @property
    def runtime_ref(self) -> str | None:
        return self._runtime_ref

    @property
    def savepoint_location(self) -> str | None:
        return self._savepoint_location

    @property
    def description(self) -> str:
        return self._description

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def submit(self, runtime_ref: str) -> None:
        self._runtime_ref = runtime_ref
        self._transition_to(JobStatus.SUBMITTED)
        self._record(JobSubmitted(job_id=self.id, runtime_ref=runtime_ref))

    def mark_running(self) -> None:
        self._transition_to(JobStatus.RUNNING)

    def suspend(self, savepoint_location: str) -> None:
        self._transition_to(JobStatus.SUSPENDED)
        self._savepoint_location = savepoint_location
        self._record(SavepointTriggered(job_id=self.id, location=savepoint_location))

    def resume(self) -> None:
        self._transition_to(JobStatus.RUNNING)

    def trigger_savepoint(self, location: str) -> None:
        if self._status is not JobStatus.RUNNING:
            raise InvalidJobTransition(self._status.value, "savepoint")
        self._savepoint_location = location
        self._touch()
        self._record(SavepointTriggered(job_id=self.id, location=location))

    def restart(self, reason: str) -> None:
        self._transition_to(JobStatus.RESTARTING)
        self._record(JobRestarted(job_id=self.id, reason=reason))

    def mark_failed(self) -> None:
        self._transition_to(JobStatus.FAILED)

    def complete(self) -> None:
        self._transition_to(JobStatus.COMPLETED)

    def cancel(self) -> None:
        self._transition_to(JobStatus.CANCELLED)

    def change_checkpoint_config(self, checkpoint: CheckpointConfig) -> None:
        _assert_exactly_once(self._sink, self._delivery_guarantee, checkpoint)
        self._checkpoint_config = checkpoint
        self._touch()

    def _transition_to(self, target: JobStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self._status]:
            raise InvalidJobTransition(self._status.value, target.value)
        previous = self._status
        self._status = target
        self._touch()
        self._record(JobStatusChanged(job_id=self.id, previous=previous, current=target))

    def _touch(self) -> None:
        self._updated_at = utcnow()
