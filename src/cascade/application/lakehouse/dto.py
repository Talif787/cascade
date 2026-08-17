from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cascade.domain.lakehouse.aggregate import Dataset
from cascade.domain.lakehouse.value_objects import (
    DatasetRef,
    QualityCheck,
    QualityOutcome,
    Schedule,
    Transformation,
)


@dataclass(frozen=True, slots=True)
class TransformationView:
    engine: str
    identifier: str
    materialization: str

    @classmethod
    def from_vo(cls, transformation: Transformation) -> TransformationView:
        return cls(
            engine=transformation.engine.value,
            identifier=transformation.identifier,
            materialization=transformation.materialization.value,
        )


@dataclass(frozen=True, slots=True)
class ScheduleView:
    cron: str
    timezone: str
    enabled: bool

    @classmethod
    def from_vo(cls, schedule: Schedule) -> ScheduleView:
        return cls(cron=schedule.cron, timezone=schedule.timezone, enabled=schedule.enabled)


@dataclass(frozen=True, slots=True)
class QualityCheckView:
    kind: str
    column: str | None
    threshold: int | None
    accepted_values: list[str]

    @classmethod
    def from_vo(cls, check: QualityCheck) -> QualityCheckView:
        return cls(
            kind=check.kind.value,
            column=check.column,
            threshold=check.threshold,
            accepted_values=list(check.accepted_values),
        )


@dataclass(frozen=True, slots=True)
class QualityOutcomeView:
    name: str
    passed: bool
    detail: str

    @classmethod
    def from_vo(cls, outcome: QualityOutcome) -> QualityOutcomeView:
        return cls(name=outcome.name, passed=outcome.passed, detail=outcome.detail)


@dataclass(frozen=True, slots=True)
class DatasetRefView:
    id: str
    name: str
    layer: str

    @classmethod
    def from_vo(cls, ref: DatasetRef) -> DatasetRefView:
        return cls(id=str(ref.dataset_id), name=str(ref.name), layer=ref.layer.value)


@dataclass(frozen=True, slots=True)
class DatasetView:
    id: str
    name: str
    layer: str
    transformation: TransformationView
    upstreams: list[DatasetRefView]
    schedule: ScheduleView
    quality_checks: list[QualityCheckView]
    contract_id: str | None
    status: str
    quality_status: str
    last_run_ref: str | None
    last_row_count: int | None
    last_materialized_at: datetime | None
    last_quality_outcomes: list[QualityOutcomeView]
    description: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_aggregate(cls, dataset: Dataset) -> DatasetView:
        return cls(
            id=str(dataset.id),
            name=str(dataset.name),
            layer=dataset.layer.value,
            transformation=TransformationView.from_vo(dataset.transformation),
            upstreams=[DatasetRefView.from_vo(ref) for ref in dataset.upstreams],
            schedule=ScheduleView.from_vo(dataset.schedule),
            quality_checks=[QualityCheckView.from_vo(c) for c in dataset.quality_checks],
            contract_id=str(dataset.contract_id) if dataset.contract_id is not None else None,
            status=dataset.status.value,
            quality_status=dataset.quality_status.value,
            last_run_ref=dataset.last_run_ref,
            last_row_count=dataset.last_row_count,
            last_materialized_at=dataset.last_materialized_at,
            last_quality_outcomes=[
                QualityOutcomeView.from_vo(o) for o in dataset.last_quality_outcomes
            ],
            description=dataset.description,
            version=dataset.version,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )


@dataclass(frozen=True, slots=True)
class LineageView:
    dataset: DatasetRefView
    upstreams: list[DatasetRefView]
    downstreams: list[DatasetRefView]
