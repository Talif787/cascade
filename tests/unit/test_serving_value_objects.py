from __future__ import annotations

import pytest

from cascade.domain.serving.errors import (
    InvalidColumn,
    InvalidExposedSchema,
    InvalidQuery,
    InvalidServingViewId,
    InvalidServingViewName,
)
from cascade.domain.serving.value_objects import (
    Column,
    ColumnRole,
    ColumnType,
    ExposedSchema,
    QueryPlan,
    ServingViewId,
    ServingViewName,
)


@pytest.mark.parametrize("value", ["analytics.orders", "serving.daily_orders", "a.b.c"])
def test_valid_names(value: str) -> None:
    assert str(ServingViewName(value)) == value


@pytest.mark.parametrize("value", ["orders", "Analytics.Orders", "a.b.c.d", "1.x", ""])
def test_invalid_names(value: str) -> None:
    with pytest.raises(InvalidServingViewName):
        ServingViewName(value)


def test_id_round_trip() -> None:
    identity = ServingViewId.new()
    assert ServingViewId.from_string(str(identity)) == identity


def test_id_rejects_non_uuid() -> None:
    with pytest.raises(InvalidServingViewId):
        ServingViewId.from_string("nope")


def test_column_rejects_bad_name() -> None:
    with pytest.raises(InvalidColumn):
        Column(name="Bad Name", type=ColumnType.STRING, role=ColumnRole.DIMENSION)


def _col(name: str, role: ColumnRole = ColumnRole.DIMENSION) -> Column:
    return Column(name=name, type=ColumnType.STRING, role=role)


def test_schema_requires_columns() -> None:
    with pytest.raises(InvalidExposedSchema):
        ExposedSchema(columns=(), order_by=())


def test_schema_rejects_duplicate_column_names() -> None:
    with pytest.raises(InvalidExposedSchema):
        ExposedSchema(columns=(_col("a"), _col("a")), order_by=("a",))


def test_schema_requires_order_by() -> None:
    with pytest.raises(InvalidExposedSchema):
        ExposedSchema(columns=(_col("a"),), order_by=())


def test_schema_order_by_must_be_declared() -> None:
    with pytest.raises(InvalidExposedSchema):
        ExposedSchema(columns=(_col("a"),), order_by=("b",))


def test_schema_partition_by_must_be_declared() -> None:
    with pytest.raises(InvalidExposedSchema):
        ExposedSchema(columns=(_col("a"),), order_by=("a",), partition_by="b")


def test_schema_column_lookup_and_measure_flag() -> None:
    schema = ExposedSchema(
        columns=(_col("region"), _col("revenue", ColumnRole.MEASURE)),
        order_by=("region",),
    )
    assert schema.column("region") is not None
    assert schema.column("missing") is None
    assert schema.has_measure() is True


def test_query_plan_requires_selection() -> None:
    with pytest.raises(InvalidQuery):
        QueryPlan(table="t", dimensions=(), measures=(), filters=(), limit=10)
