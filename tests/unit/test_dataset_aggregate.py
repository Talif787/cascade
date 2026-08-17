from __future__ import annotations

import pytest

from cascade.domain.lakehouse.aggregate import Dataset
from cascade.domain.lakehouse.errors import (
    InvalidDatasetTransition,
    InvalidMedallionDependency,
)
from cascade.domain.lakehouse.events import (
    DatasetMaterialized,
    DatasetRegistered,
    QualityEvaluated,
)
from cascade.domain.lakehouse.value_objects import (
    DatasetId,
    DatasetName,
    DatasetRef,
    DatasetStatus,
    Materialization,
    MedallionLayer,
    QualityCheck,
    QualityCheckKind,
    QualityOutcome,
    QualityStatus,
    Schedule,
    Transformation,
    TransformationEngine,
)


def _transformation() -> Transformation:
    return Transformation(
        engine=TransformationEngine.DBT,
        identifier="model_x",
        materialization=Materialization.TABLE,
    )


def _schedule() -> Schedule:
    return Schedule(cron="0 2 * * *", timezone="UTC", enabled=True)


def _ref(layer: MedallionLayer, name: str) -> DatasetRef:
    return DatasetRef(dataset_id=DatasetId.new(), name=DatasetName(name), layer=layer)


def _dataset(
    *,
    name: str = "silver.orders_enriched",
    layer: MedallionLayer = MedallionLayer.SILVER,
    upstreams: tuple[DatasetRef, ...] = (),
    quality_checks: tuple[QualityCheck, ...] = (),
) -> Dataset:
    return Dataset.register(
        name=DatasetName(name),
        layer=layer,
        transformation=_transformation(),
        schedule=_schedule(),
        upstreams=upstreams,
        quality_checks=quality_checks,
    )


def test_register_starts_in_registered_state() -> None:
    dataset = _dataset()
    assert dataset.status is DatasetStatus.REGISTERED
    assert dataset.quality_status is QualityStatus.UNKNOWN
    assert any(isinstance(e, DatasetRegistered) for e in dataset.pull_events())


def test_silver_may_depend_on_bronze() -> None:
    dataset = _dataset(upstreams=(_ref(MedallionLayer.BRONZE, "bronze.orders"),))
    assert len(dataset.upstreams) == 1


def test_gold_may_depend_on_silver() -> None:
    dataset = _dataset(
        name="gold.orders_daily",
        layer=MedallionLayer.GOLD,
        upstreams=(_ref(MedallionLayer.SILVER, "silver.orders"),),
    )
    assert dataset.layer is MedallionLayer.GOLD


def test_silver_cannot_depend_on_gold() -> None:
    with pytest.raises(InvalidMedallionDependency):
        _dataset(upstreams=(_ref(MedallionLayer.GOLD, "gold.summary"),))


def test_bronze_cannot_depend_on_silver() -> None:
    with pytest.raises(InvalidMedallionDependency):
        _dataset(
            name="bronze.raw",
            layer=MedallionLayer.BRONZE,
            upstreams=(_ref(MedallionLayer.SILVER, "silver.orders"),),
        )


def test_duplicate_dependency_is_rejected() -> None:
    ref = _ref(MedallionLayer.BRONZE, "bronze.orders")
    with pytest.raises(InvalidMedallionDependency):
        _dataset(upstreams=(ref, ref))


def test_materialization_success_marks_materialized_and_quality_passed() -> None:
    dataset = _dataset(quality_checks=(QualityCheck(kind=QualityCheckKind.NOT_NULL, column="id"),))
    dataset.pull_events()
    dataset.begin_materialization("run-1")
    assert dataset.status is DatasetStatus.MATERIALIZING
    dataset.complete_materialization(
        "run-1", 500, (QualityOutcome(name="not_null:id", passed=True),)
    )
    assert dataset.status is DatasetStatus.MATERIALIZED
    assert dataset.quality_status is QualityStatus.PASSED
    assert dataset.last_row_count == 500
    events = dataset.pull_events()
    assert any(isinstance(e, DatasetMaterialized) for e in events)
    assert any(isinstance(e, QualityEvaluated) for e in events)


def test_failing_quality_marks_dataset_failed() -> None:
    dataset = _dataset(quality_checks=(QualityCheck(kind=QualityCheckKind.NOT_NULL, column="id"),))
    dataset.begin_materialization("run-2")
    dataset.complete_materialization(
        "run-2", 500, (QualityOutcome(name="not_null:id", passed=False, detail="nulls found"),)
    )
    assert dataset.status is DatasetStatus.FAILED
    assert dataset.quality_status is QualityStatus.FAILED


def test_runtime_failure_marks_dataset_failed() -> None:
    dataset = _dataset()
    dataset.begin_materialization("run-3")
    dataset.fail_materialization("engine crashed")
    assert dataset.status is DatasetStatus.FAILED


def test_materialized_can_be_marked_stale_then_rematerialized() -> None:
    dataset = _dataset()
    dataset.begin_materialization("run-4")
    dataset.complete_materialization("run-4", 10, ())
    assert dataset.status is DatasetStatus.MATERIALIZED
    dataset.mark_stale()
    assert dataset.status is DatasetStatus.STALE
    dataset.begin_materialization("run-5")
    assert dataset.status is DatasetStatus.MATERIALIZING


def test_mark_stale_is_a_noop_when_not_materialized() -> None:
    dataset = _dataset()
    dataset.mark_stale()
    assert dataset.status is DatasetStatus.REGISTERED


def test_deprecate_is_terminal() -> None:
    dataset = _dataset()
    dataset.deprecate()
    assert dataset.status is DatasetStatus.DEPRECATED
    with pytest.raises(InvalidDatasetTransition):
        dataset.begin_materialization("run-x")


def test_change_schedule_records_event() -> None:
    dataset = _dataset()
    dataset.pull_events()
    dataset.change_schedule(Schedule(cron="*/15 * * * *", timezone="UTC", enabled=False))
    assert dataset.schedule.enabled is False
    assert dataset.schedule.cron == "*/15 * * * *"


def test_depends_on_detects_upstream() -> None:
    ref = _ref(MedallionLayer.BRONZE, "bronze.orders")
    dataset = _dataset(upstreams=(ref,))
    assert dataset.depends_on(ref.dataset_id) is True
    assert dataset.depends_on(DatasetId.new()) is False
