from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import AggregateRoot, utcnow
from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.lakehouse.errors import (
    InvalidDatasetTransition,
    InvalidMedallionDependency,
)
from cascade.domain.lakehouse.events import (
    DatasetMaterialized,
    DatasetRegistered,
    DatasetStatusChanged,
    MaterializationFailed,
    MaterializationStarted,
    QualityEvaluated,
    ScheduleChanged,
)
from cascade.domain.lakehouse.value_objects import (
    DatasetId,
    DatasetName,
    DatasetRef,
    DatasetStatus,
    MedallionLayer,
    QualityCheck,
    QualityOutcome,
    QualityStatus,
    Schedule,
    Transformation,
    layer_rank,
)

_MAX_DESCRIPTION_LEN = 1024

_ALLOWED_TRANSITIONS: dict[DatasetStatus, frozenset[DatasetStatus]] = {
    DatasetStatus.REGISTERED: frozenset({DatasetStatus.MATERIALIZING, DatasetStatus.DEPRECATED}),
    DatasetStatus.MATERIALIZING: frozenset(
        {DatasetStatus.MATERIALIZED, DatasetStatus.FAILED, DatasetStatus.DEPRECATED}
    ),
    DatasetStatus.MATERIALIZED: frozenset(
        {DatasetStatus.MATERIALIZING, DatasetStatus.STALE, DatasetStatus.DEPRECATED}
    ),
    DatasetStatus.STALE: frozenset({DatasetStatus.MATERIALIZING, DatasetStatus.DEPRECATED}),
    DatasetStatus.FAILED: frozenset({DatasetStatus.MATERIALIZING, DatasetStatus.DEPRECATED}),
    DatasetStatus.DEPRECATED: frozenset(),
}


def _validate_dependencies(
    dataset_id: DatasetId, layer: MedallionLayer, upstreams: tuple[DatasetRef, ...]
) -> None:
    seen: set[str] = set()
    rank = layer_rank(layer)
    for ref in upstreams:
        if ref.dataset_id == dataset_id:
            raise InvalidMedallionDependency("a dataset cannot depend on itself")
        key = str(ref.dataset_id)
        if key in seen:
            raise InvalidMedallionDependency(f"duplicate dependency on {ref.name!s}")
        seen.add(key)
        if layer_rank(ref.layer) > rank:
            raise InvalidMedallionDependency(
                f"a {layer.value} dataset cannot depend on the higher layer "
                f"{ref.layer.value} ({ref.name!s})"
            )


class Dataset(AggregateRoot[DatasetId]):
    """A managed medallion table with a transformation, schedule, and quality checks."""

    def __init__(
        self,
        dataset_id: DatasetId,
        *,
        name: DatasetName,
        layer: MedallionLayer,
        transformation: Transformation,
        upstreams: tuple[DatasetRef, ...],
        schedule: Schedule,
        quality_checks: tuple[QualityCheck, ...],
        contract_id: DataContractId | None,
        status: DatasetStatus,
        quality_status: QualityStatus,
        last_run_ref: str | None,
        last_row_count: int | None,
        last_materialized_at: datetime | None,
        last_quality_outcomes: tuple[QualityOutcome, ...],
        description: str,
        created_at: datetime,
        updated_at: datetime,
        version: int = 0,
    ) -> None:
        super().__init__(dataset_id, version=version)
        self._name = name
        self._layer = layer
        self._transformation = transformation
        self._upstreams = upstreams
        self._schedule = schedule
        self._quality_checks = quality_checks
        self._contract_id = contract_id
        self._status = status
        self._quality_status = quality_status
        self._last_run_ref = last_run_ref
        self._last_row_count = last_row_count
        self._last_materialized_at = last_materialized_at
        self._last_quality_outcomes = last_quality_outcomes
        self._description = description
        self._created_at = created_at
        self._updated_at = updated_at

    @classmethod
    def register(
        cls,
        *,
        name: DatasetName,
        layer: MedallionLayer,
        transformation: Transformation,
        schedule: Schedule,
        upstreams: tuple[DatasetRef, ...] = (),
        quality_checks: tuple[QualityCheck, ...] = (),
        contract_id: DataContractId | None = None,
        description: str = "",
    ) -> Dataset:
        dataset_id = DatasetId.new()
        _validate_dependencies(dataset_id, layer, upstreams)
        now = utcnow()
        dataset = cls(
            dataset_id,
            name=name,
            layer=layer,
            transformation=transformation,
            upstreams=upstreams,
            schedule=schedule,
            quality_checks=quality_checks,
            contract_id=contract_id,
            status=DatasetStatus.REGISTERED,
            quality_status=QualityStatus.UNKNOWN,
            last_run_ref=None,
            last_row_count=None,
            last_materialized_at=None,
            last_quality_outcomes=(),
            description=description.strip()[:_MAX_DESCRIPTION_LEN],
            created_at=now,
            updated_at=now,
        )
        dataset._record(DatasetRegistered(dataset_id=dataset.id, name=str(name), layer=layer.value))
        return dataset

    @property
    def name(self) -> DatasetName:
        return self._name

    @property
    def layer(self) -> MedallionLayer:
        return self._layer

    @property
    def transformation(self) -> Transformation:
        return self._transformation

    @property
    def upstreams(self) -> tuple[DatasetRef, ...]:
        return self._upstreams

    @property
    def schedule(self) -> Schedule:
        return self._schedule

    @property
    def quality_checks(self) -> tuple[QualityCheck, ...]:
        return self._quality_checks

    @property
    def contract_id(self) -> DataContractId | None:
        return self._contract_id

    @property
    def status(self) -> DatasetStatus:
        return self._status

    @property
    def quality_status(self) -> QualityStatus:
        return self._quality_status

    @property
    def last_run_ref(self) -> str | None:
        return self._last_run_ref

    @property
    def last_row_count(self) -> int | None:
        return self._last_row_count

    @property
    def last_materialized_at(self) -> datetime | None:
        return self._last_materialized_at

    @property
    def last_quality_outcomes(self) -> tuple[QualityOutcome, ...]:
        return self._last_quality_outcomes

    @property
    def description(self) -> str:
        return self._description

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def depends_on(self, dataset_id: DatasetId) -> bool:
        return any(ref.dataset_id == dataset_id for ref in self._upstreams)

    def begin_materialization(self, run_ref: str) -> None:
        self._transition_to(DatasetStatus.MATERIALIZING)
        self._last_run_ref = run_ref
        self._record(MaterializationStarted(dataset_id=self.id, run_ref=run_ref))

    def complete_materialization(
        self, run_ref: str, row_count: int, outcomes: tuple[QualityOutcome, ...]
    ) -> None:
        self._last_run_ref = run_ref
        self._last_row_count = row_count
        self._last_materialized_at = utcnow()
        self._last_quality_outcomes = outcomes
        self._record(DatasetMaterialized(dataset_id=self.id, run_ref=run_ref, row_count=row_count))
        passed = sum(1 for outcome in outcomes if outcome.passed)
        failed = len(outcomes) - passed
        self._quality_status = QualityStatus.FAILED if failed else QualityStatus.PASSED
        self._record(
            QualityEvaluated(
                dataset_id=self.id,
                status=self._quality_status,
                passed=passed,
                failed=failed,
            )
        )
        if failed:
            self._transition_to(DatasetStatus.FAILED)
        else:
            self._transition_to(DatasetStatus.MATERIALIZED)

    def fail_materialization(self, reason: str) -> None:
        self._transition_to(DatasetStatus.FAILED)
        self._record(MaterializationFailed(dataset_id=self.id, reason=reason))

    def mark_stale(self) -> None:
        if self._status is not DatasetStatus.MATERIALIZED:
            return
        self._transition_to(DatasetStatus.STALE)

    def change_schedule(self, schedule: Schedule) -> None:
        self._schedule = schedule
        self._touch()
        self._record(ScheduleChanged(dataset_id=self.id, enabled=schedule.enabled))

    def deprecate(self) -> None:
        self._transition_to(DatasetStatus.DEPRECATED)

    def _transition_to(self, target: DatasetStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self._status]:
            raise InvalidDatasetTransition(self._status.value, target.value)
        previous = self._status
        self._status = target
        self._touch()
        self._record(DatasetStatusChanged(dataset_id=self.id, previous=previous, current=target))

    def _touch(self) -> None:
        self._updated_at = utcnow()
