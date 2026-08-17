from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import AggregateRoot, utcnow
from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.ingestion.errors import InvalidSourceTransition
from cascade.domain.ingestion.events import (
    DeadLettersRecorded,
    DeadLetterThresholdBreached,
    IngestionSourceRegistered,
    SourceProvisioned,
    SourceStatusChanged,
)
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

_MAX_DESCRIPTION_LEN = 1024

_ALLOWED_TRANSITIONS: dict[SourceStatus, frozenset[SourceStatus]] = {
    SourceStatus.REGISTERED: frozenset({SourceStatus.PROVISIONING, SourceStatus.DECOMMISSIONED}),
    SourceStatus.PROVISIONING: frozenset(
        {SourceStatus.RUNNING, SourceStatus.FAILED, SourceStatus.DECOMMISSIONED}
    ),
    SourceStatus.RUNNING: frozenset(
        {SourceStatus.PAUSED, SourceStatus.FAILED, SourceStatus.DECOMMISSIONED}
    ),
    SourceStatus.PAUSED: frozenset({SourceStatus.RUNNING, SourceStatus.DECOMMISSIONED}),
    SourceStatus.FAILED: frozenset({SourceStatus.PROVISIONING, SourceStatus.DECOMMISSIONED}),
    SourceStatus.DECOMMISSIONED: frozenset(),
}


class IngestionSource(AggregateRoot[IngestionSourceId]):
    """A managed connection that ingests data from an external system."""

    def __init__(
        self,
        source_id: IngestionSourceId,
        *,
        name: SourceName,
        connector_kind: ConnectorKind,
        config: ConnectorConfig,
        contract_id: DataContractId,
        pipeline_id: PipelineId | None,
        status: SourceStatus,
        dead_letter_policy: DeadLetterPolicy,
        dead_letter_count: int,
        runtime_ref: str | None,
        description: str,
        created_at: datetime,
        updated_at: datetime,
        version: int = 0,
    ) -> None:
        super().__init__(source_id, version=version)
        self._name = name
        self._connector_kind = connector_kind
        self._config = config
        self._contract_id = contract_id
        self._pipeline_id = pipeline_id
        self._status = status
        self._dead_letter_policy = dead_letter_policy
        self._dead_letter_count = dead_letter_count
        self._runtime_ref = runtime_ref
        self._description = description
        self._created_at = created_at
        self._updated_at = updated_at

    @classmethod
    def register(
        cls,
        *,
        name: SourceName,
        connector_kind: ConnectorKind,
        config: ConnectorConfig,
        contract_id: DataContractId,
        dead_letter_policy: DeadLetterPolicy,
        pipeline_id: PipelineId | None = None,
        description: str = "",
    ) -> IngestionSource:
        now = utcnow()
        source = cls(
            IngestionSourceId.new(),
            name=name,
            connector_kind=connector_kind,
            config=config,
            contract_id=contract_id,
            pipeline_id=pipeline_id,
            status=SourceStatus.REGISTERED,
            dead_letter_policy=dead_letter_policy,
            dead_letter_count=0,
            runtime_ref=None,
            description=description.strip()[:_MAX_DESCRIPTION_LEN],
            created_at=now,
            updated_at=now,
        )
        source._record(IngestionSourceRegistered(source_id=source.id, name=str(name)))
        return source

    @property
    def name(self) -> SourceName:
        return self._name

    @property
    def connector_kind(self) -> ConnectorKind:
        return self._connector_kind

    @property
    def config(self) -> ConnectorConfig:
        return self._config

    @property
    def contract_id(self) -> DataContractId:
        return self._contract_id

    @property
    def pipeline_id(self) -> PipelineId | None:
        return self._pipeline_id

    @property
    def status(self) -> SourceStatus:
        return self._status

    @property
    def dead_letter_policy(self) -> DeadLetterPolicy:
        return self._dead_letter_policy

    @property
    def dead_letter_count(self) -> int:
        return self._dead_letter_count

    @property
    def runtime_ref(self) -> str | None:
        return self._runtime_ref

    @property
    def description(self) -> str:
        return self._description

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def begin_provisioning(self) -> None:
        self._transition_to(SourceStatus.PROVISIONING)

    def mark_running(self, runtime_ref: str) -> None:
        first_time = self._runtime_ref is None
        self._runtime_ref = runtime_ref
        self._transition_to(SourceStatus.RUNNING)
        if first_time:
            self._record(SourceProvisioned(source_id=self.id, runtime_ref=runtime_ref))

    def pause(self) -> None:
        self._transition_to(SourceStatus.PAUSED)

    def resume(self) -> None:
        self._transition_to(SourceStatus.RUNNING)

    def mark_failed(self) -> None:
        self._transition_to(SourceStatus.FAILED)

    def decommission(self) -> None:
        self._transition_to(SourceStatus.DECOMMISSIONED)

    def change_dead_letter_policy(self, policy: DeadLetterPolicy) -> None:
        self._dead_letter_policy = policy
        self._touch()

    def record_dead_letters(self, count: int) -> None:
        if count <= 0:
            return
        self._dead_letter_count += count
        self._touch()
        self._record(
            DeadLettersRecorded(source_id=self.id, added=count, total=self._dead_letter_count)
        )
        policy = self._dead_letter_policy
        if policy.trips_on_breach and self._dead_letter_count >= policy.tolerance:
            self._record(
                DeadLetterThresholdBreached(
                    source_id=self.id,
                    total=self._dead_letter_count,
                    tolerance=policy.tolerance,
                )
            )
            if policy.on_failure is FailureAction.HALT and self._status is SourceStatus.RUNNING:
                self._transition_to(SourceStatus.FAILED)

    def _transition_to(self, target: SourceStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self._status]:
            raise InvalidSourceTransition(self._status.value, target.value)
        previous = self._status
        self._status = target
        self._touch()
        self._record(SourceStatusChanged(source_id=self.id, previous=previous, current=target))

    def _touch(self) -> None:
        self._updated_at = utcnow()
