from __future__ import annotations

from cascade.application.serving.runtime import CompiledQuery, ServingTableSpec
from cascade.domain.serving.value_objects import (
    Aggregation,
    ClickHouseEngine,
    ColumnType,
    FilterOp,
)

_ENGINE_SQL = {
    ClickHouseEngine.MERGE_TREE: "MergeTree",
    ClickHouseEngine.REPLACING_MERGE_TREE: "ReplacingMergeTree",
    ClickHouseEngine.SUMMING_MERGE_TREE: "SummingMergeTree",
    ClickHouseEngine.AGGREGATING_MERGE_TREE: "AggregatingMergeTree",
}

_TYPE_SQL = {
    ColumnType.STRING: "String",
    ColumnType.INT: "Int64",
    ColumnType.FLOAT: "Float64",
    ColumnType.BOOL: "UInt8",
    ColumnType.DATE: "Date",
    ColumnType.DATETIME: "DateTime",
}

_AGG_SQL = {
    Aggregation.SUM: "sum",
    Aggregation.AVG: "avg",
    Aggregation.MIN: "min",
    Aggregation.MAX: "max",
    Aggregation.COUNT: "count",
}

_OP_SQL = {
    FilterOp.EQ: "=",
    FilterOp.NEQ: "!=",
    FilterOp.GT: ">",
    FilterOp.GTE: ">=",
    FilterOp.LT: "<",
    FilterOp.LTE: "<=",
}


def _column_sql(name: str, type_sql: str, nullable: bool) -> str:
    rendered = f"Nullable({type_sql})" if nullable else type_sql
    return f"{name} {rendered}"


def build_create_table_sql(spec: ServingTableSpec) -> str:
    columns = ", ".join(_column_sql(c.name, _TYPE_SQL[c.type], c.nullable) for c in spec.columns)
    engine = _ENGINE_SQL[spec.engine]
    order_by = ", ".join(spec.order_by)
    clauses = [
        f"CREATE TABLE IF NOT EXISTS {spec.name} ({columns})",
        f"ENGINE = {engine}()",
    ]
    if spec.partition_by is not None:
        clauses.append(f"PARTITION BY {spec.partition_by}")
    clauses.append(f"ORDER BY ({order_by})")
    return " ".join(clauses)


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _filter_sql(column: str, op: FilterOp, values: tuple[str, ...]) -> str:
    if op is FilterOp.IN:
        rendered = ", ".join(_quote(v) for v in values)
        return f"{column} IN ({rendered})"
    value = _quote(values[0]) if values else "''"
    return f"{column} {_OP_SQL[op]} {value}"


def build_select_sql(compiled: CompiledQuery) -> str:
    select_parts = list(compiled.dimensions)
    for measure in compiled.measures:
        agg = _AGG_SQL[measure.aggregation]
        alias = f"{measure.aggregation.value}_{measure.column}"
        select_parts.append(f"{agg}({measure.column}) AS {alias}")
    select_clause = ", ".join(select_parts) if select_parts else "*"

    sql = f"SELECT {select_clause} FROM {compiled.table}"
    if compiled.filters:
        conditions = " AND ".join(_filter_sql(f.column, f.op, f.values) for f in compiled.filters)
        sql += f" WHERE {conditions}"
    if compiled.dimensions and compiled.measures:
        sql += " GROUP BY " + ", ".join(compiled.dimensions)
    sql += f" LIMIT {compiled.limit}"
    return sql
