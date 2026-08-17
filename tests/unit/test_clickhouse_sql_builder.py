from __future__ import annotations

from cascade.application.serving.runtime import CompiledQuery, ServingTableSpec
from cascade.domain.serving.value_objects import (
    Aggregation,
    ClickHouseEngine,
    Column,
    ColumnRole,
    ColumnType,
    FilterClause,
    FilterOp,
    MeasureSelection,
)
from cascade.infrastructure.clickhouse.sql_builder import (
    build_create_table_sql,
    build_select_sql,
)


def _spec(engine: ClickHouseEngine = ClickHouseEngine.MERGE_TREE) -> ServingTableSpec:
    return ServingTableSpec(
        name="analytics.orders_daily",
        engine=engine,
        columns=(
            Column(name="day", type=ColumnType.DATE, role=ColumnRole.TIME),
            Column(name="region", type=ColumnType.STRING, role=ColumnRole.DIMENSION),
            Column(
                name="revenue",
                type=ColumnType.FLOAT,
                role=ColumnRole.MEASURE,
                nullable=True,
            ),
        ),
        order_by=("day", "region"),
        partition_by="day",
        source_table="gold.orders_daily",
    )


def test_create_table_sql_renders_engine_and_keys() -> None:
    sql = build_create_table_sql(_spec(ClickHouseEngine.AGGREGATING_MERGE_TREE))
    assert "CREATE TABLE IF NOT EXISTS analytics.orders_daily" in sql
    assert "day Date" in sql
    assert "region String" in sql
    assert "revenue Nullable(Float64)" in sql
    assert "ENGINE = AggregatingMergeTree()" in sql
    assert "PARTITION BY day" in sql
    assert "ORDER BY (day, region)" in sql


def test_select_sql_with_group_by_and_filters() -> None:
    compiled = CompiledQuery(
        table="analytics.orders_daily",
        dimensions=("region",),
        measures=(MeasureSelection(column="revenue", aggregation=Aggregation.SUM),),
        filters=(FilterClause(column="region", op=FilterOp.EQ, values=("us",)),),
        limit=25,
    )
    sql = build_select_sql(compiled)
    assert sql.startswith("SELECT region, sum(revenue) AS sum_revenue FROM analytics.orders_daily")
    assert "WHERE region = 'us'" in sql
    assert "GROUP BY region" in sql
    assert sql.endswith("LIMIT 25")


def test_select_sql_in_filter_and_no_group_by() -> None:
    compiled = CompiledQuery(
        table="analytics.orders_daily",
        dimensions=("region",),
        measures=(),
        filters=(FilterClause(column="region", op=FilterOp.IN, values=("us", "eu")),),
        limit=10,
    )
    sql = build_select_sql(compiled)
    assert "WHERE region IN ('us', 'eu')" in sql
    assert "GROUP BY" not in sql


def test_select_sql_escapes_quotes() -> None:
    compiled = CompiledQuery(
        table="t",
        dimensions=("region",),
        measures=(),
        filters=(FilterClause(column="region", op=FilterOp.EQ, values=("O'Brien",)),),
        limit=5,
    )
    sql = build_select_sql(compiled)
    assert "region = 'O''Brien'" in sql
