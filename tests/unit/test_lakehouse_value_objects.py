from __future__ import annotations

import pytest

from cascade.domain.lakehouse.errors import (
    InvalidDatasetId,
    InvalidDatasetName,
    InvalidQualityCheck,
    InvalidSchedule,
    InvalidTransformation,
)
from cascade.domain.lakehouse.value_objects import (
    DatasetId,
    DatasetName,
    MedallionLayer,
    QualityCheck,
    QualityCheckKind,
    Schedule,
    Transformation,
    TransformationEngine,
    layer_rank,
)


@pytest.mark.parametrize("value", ["bronze.orders", "silver.orders_enriched", "cat.ns.table"])
def test_valid_dataset_names(value: str) -> None:
    assert str(DatasetName(value)) == value


@pytest.mark.parametrize("value", ["orders", "Silver.Orders", "a.b.c.d", "1.x", ""])
def test_invalid_dataset_names(value: str) -> None:
    with pytest.raises(InvalidDatasetName):
        DatasetName(value)


def test_dataset_id_round_trip() -> None:
    identity = DatasetId.new()
    assert DatasetId.from_string(str(identity)) == identity


def test_dataset_id_rejects_non_uuid() -> None:
    with pytest.raises(InvalidDatasetId):
        DatasetId.from_string("nope")


def test_layer_rank_ordering() -> None:
    assert layer_rank(MedallionLayer.BRONZE) < layer_rank(MedallionLayer.SILVER)
    assert layer_rank(MedallionLayer.SILVER) < layer_rank(MedallionLayer.GOLD)


def test_transformation_requires_identifier() -> None:
    with pytest.raises(InvalidTransformation):
        Transformation(engine=TransformationEngine.DBT, identifier="  ")


def test_schedule_requires_five_cron_fields() -> None:
    with pytest.raises(InvalidSchedule):
        Schedule(cron="0 2 * *")


def test_schedule_accepts_valid_cron() -> None:
    schedule = Schedule(cron="0 2 * * *", timezone="UTC")
    assert schedule.enabled is True


def test_not_null_check_requires_column() -> None:
    with pytest.raises(InvalidQualityCheck):
        QualityCheck(kind=QualityCheckKind.NOT_NULL)


def test_accepted_values_requires_column_and_values() -> None:
    with pytest.raises(InvalidQualityCheck):
        QualityCheck(kind=QualityCheckKind.ACCEPTED_VALUES, column="status")


def test_row_count_min_requires_non_negative_threshold() -> None:
    with pytest.raises(InvalidQualityCheck):
        QualityCheck(kind=QualityCheckKind.ROW_COUNT_MIN, threshold=-1)


def test_freshness_requires_positive_threshold() -> None:
    with pytest.raises(InvalidQualityCheck):
        QualityCheck(kind=QualityCheckKind.FRESHNESS, threshold=0)


def test_quality_check_name_includes_column() -> None:
    check = QualityCheck(kind=QualityCheckKind.UNIQUE, column="order_id")
    assert check.name == "unique:order_id"
