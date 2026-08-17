from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cascade.domain.lakehouse.value_objects import DatasetId
from cascade.domain.serving.aggregate import ServingView
from cascade.domain.serving.errors import (
    InvalidQuery,
    InvalidServingEngine,
    InvalidServingTransition,
    ViewNotQueryable,
)
from cascade.domain.serving.events import (
    ServingViewRegistered,
    ServingViewSynced,
)
from cascade.domain.serving.value_objects import (
    Aggregation,
    ClickHouseEngine,
    Column,
    ColumnRole,
    ColumnType,
    ExposedSchema,
    FilterClause,
    FilterOp,
    MeasureSelection,
    QueryRequest,
    RefreshMode,
    ServingStatus,
    ServingViewName,
)


def _schema(with_measure: bool = True) -> ExposedSchema:
    columns = [
        Column(name="day", type=ColumnType.DATE, role=ColumnRole.TIME),
        Column(name="region", type=ColumnType.STRING, role=ColumnRole.DIMENSION),
    ]
    if with_measure:
        columns.append(Column(name="revenue", type=ColumnType.FLOAT, role=ColumnRole.MEASURE))
    return ExposedSchema(columns=tuple(columns), order_by=("day",))


def _view(
    *,
    engine: ClickHouseEngine = ClickHouseEngine.MERGE_TREE,
    with_measure: bool = True,
) -> ServingView:
    return ServingView.register(
        name=ServingViewName("analytics.orders_daily"),
        source_dataset_id=DatasetId.new(),
        engine=engine,
        schema=_schema(with_measure),
        refresh_mode=RefreshMode.FULL,
    )


def test_register_starts_in_registered_state() -> None:
    view = _view()
    assert view.status is ServingStatus.REGISTERED
    assert any(isinstance(e, ServingViewRegistered) for e in view.pull_events())


def test_aggregating_engine_requires_a_measure() -> None:
    with pytest.raises(InvalidServingEngine):
        _view(engine=ClickHouseEngine.AGGREGATING_MERGE_TREE, with_measure=False)


def test_summing_engine_requires_a_measure() -> None:
    with pytest.raises(InvalidServingEngine):
        _view(engine=ClickHouseEngine.SUMMING_MERGE_TREE, with_measure=False)


def test_merge_tree_allows_no_measure() -> None:
    view = _view(engine=ClickHouseEngine.MERGE_TREE, with_measure=False)
    assert view.engine is ClickHouseEngine.MERGE_TREE


def test_sync_lifecycle_to_ready() -> None:
    view = _view()
    view.pull_events()
    view.begin_sync("s1")
    assert view.status is ServingStatus.SYNCING
    view.complete_sync("s1", 100, datetime.now(UTC))
    assert view.status is ServingStatus.READY
    assert view.last_row_count == 100
    assert any(isinstance(e, ServingViewSynced) for e in view.pull_events())


def test_failed_sync_can_be_retried() -> None:
    view = _view()
    view.begin_sync("s1")
    view.fail_sync("boom")
    assert view.status is ServingStatus.FAILED
    view.begin_sync("s2")
    assert view.status is ServingStatus.SYNCING


def test_reconcile_marks_stale_when_source_is_newer() -> None:
    synced = datetime.now(UTC)
    view = _view()
    view.begin_sync("s1")
    view.complete_sync("s1", 10, synced)
    assert view.reconcile(synced + timedelta(hours=1)) is True
    assert view.status is ServingStatus.STALE


def test_reconcile_no_change_when_source_not_newer() -> None:
    synced = datetime.now(UTC)
    view = _view()
    view.begin_sync("s1")
    view.complete_sync("s1", 10, synced)
    assert view.reconcile(synced - timedelta(hours=1)) is False
    assert view.status is ServingStatus.READY


def test_retire_is_terminal() -> None:
    view = _view()
    view.retire()
    assert view.status is ServingStatus.RETIRED
    with pytest.raises(InvalidServingTransition):
        view.begin_sync("s1")


def test_query_requires_ready_or_stale() -> None:
    view = _view()
    with pytest.raises(ViewNotQueryable):
        view.plan_query(QueryRequest(dimensions=("region",)))


def _ready_view() -> ServingView:
    view = _view()
    view.begin_sync("s1")
    view.complete_sync("s1", 10, datetime.now(UTC))
    return view


def test_plan_query_accepts_valid_dimensions_and_measures() -> None:
    view = _ready_view()
    plan = view.plan_query(
        QueryRequest(
            dimensions=("region",),
            measures=(MeasureSelection(column="revenue", aggregation=Aggregation.SUM),),
            filters=(FilterClause(column="region", op=FilterOp.EQ, values=("us",)),),
            limit=50,
        )
    )
    assert plan.table == "analytics.orders_daily"
    assert plan.dimensions == ("region",)
    assert plan.limit == 50


def test_plan_query_rejects_unknown_dimension() -> None:
    view = _ready_view()
    with pytest.raises(InvalidQuery):
        view.plan_query(QueryRequest(dimensions=("nope",)))


def test_plan_query_rejects_measure_used_as_dimension() -> None:
    view = _ready_view()
    with pytest.raises(InvalidQuery):
        view.plan_query(QueryRequest(dimensions=("revenue",)))


def test_plan_query_rejects_dimension_used_as_measure() -> None:
    view = _ready_view()
    with pytest.raises(InvalidQuery):
        view.plan_query(
            QueryRequest(measures=(MeasureSelection(column="region", aggregation=Aggregation.SUM),))
        )


def test_plan_query_clamps_limit() -> None:
    view = _ready_view()
    plan = view.plan_query(QueryRequest(dimensions=("region",), limit=99_999))
    assert plan.limit == 10_000


def test_change_schedule_updates_fields() -> None:
    view = _view()
    view.pull_events()
    view.change_schedule("0 6 * * *", False)
    assert view.refresh_cron == "0 6 * * *"
    assert view.refresh_enabled is False
