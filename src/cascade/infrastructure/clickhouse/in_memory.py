from __future__ import annotations

import uuid
from typing import Any

from cascade.application.serving.runtime import (
    ClickHouseRuntime,
    CompiledQuery,
    QueryResult,
    ServingTableSpec,
    SyncResult,
)
from cascade.domain.serving.value_objects import (
    Aggregation,
    ColumnType,
    FilterOp,
)

_DEFAULT_ROWS = 24


def _synthetic_value(column_type: ColumnType, seed: int) -> Any:
    if column_type is ColumnType.STRING:
        return f"value_{seed % 4}"
    if column_type is ColumnType.INT:
        return seed % 100
    if column_type is ColumnType.FLOAT:
        return float(seed % 100) + 0.5
    if column_type is ColumnType.BOOL:
        return seed % 2
    if column_type is ColumnType.DATE:
        return f"2026-01-{(seed % 28) + 1:02d}"
    return f"2026-01-{(seed % 28) + 1:02d} 00:00:00"


class InMemoryClickHouseRuntime(ClickHouseRuntime):
    """Simulates ClickHouse in process, including query execution over stored rows."""

    def __init__(self, rows_per_sync: int = _DEFAULT_ROWS) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._specs: dict[str, ServingTableSpec] = {}
        self._rows_per_sync = rows_per_sync

    async def create_or_replace(self, spec: ServingTableSpec) -> None:
        self._specs[spec.name] = spec
        self._tables.setdefault(spec.name, [])

    async def sync(self, spec: ServingTableSpec) -> SyncResult:
        self._specs[spec.name] = spec
        rows: list[dict[str, Any]] = []
        for i in range(self._rows_per_sync):
            row = {c.name: _synthetic_value(c.type, i) for c in spec.columns}
            rows.append(row)
        self._tables[spec.name] = rows
        return SyncResult(sync_ref=f"ch-sync-{uuid.uuid4().hex[:12]}", row_count=len(rows))

    async def drop(self, name: str) -> None:
        self._tables.pop(name, None)
        self._specs.pop(name, None)

    async def query(self, compiled: CompiledQuery) -> QueryResult:
        rows = self._tables.get(compiled.table, [])
        rows = [r for r in rows if _matches(r, compiled)]

        if compiled.measures and compiled.dimensions:
            grouped = _group_and_aggregate(rows, compiled)
            columns = tuple(compiled.dimensions) + tuple(
                f"{m.aggregation.value}_{m.column}" for m in compiled.measures
            )
            return QueryResult(columns=columns, rows=tuple(grouped[: compiled.limit]))

        if compiled.measures:
            aggregated = _aggregate_all(rows, compiled)
            columns = tuple(f"{m.aggregation.value}_{m.column}" for m in compiled.measures)
            return QueryResult(columns=columns, rows=(aggregated,))

        projected = [
            {dim: r.get(dim) for dim in compiled.dimensions} for r in rows[: compiled.limit]
        ]
        return QueryResult(columns=tuple(compiled.dimensions), rows=tuple(projected))


def _matches(row: dict[str, Any], compiled: CompiledQuery) -> bool:
    for clause in compiled.filters:
        actual = row.get(clause.column)
        if not _match_clause(actual, clause.op, clause.values):
            return False
    return True


def _match_clause(actual: Any, op: FilterOp, values: tuple[str, ...]) -> bool:
    if op is FilterOp.IN:
        return str(actual) in set(values)
    expected = values[0] if values else ""
    actual_s = str(actual)
    if op is FilterOp.EQ:
        return actual_s == expected
    if op is FilterOp.NEQ:
        return actual_s != expected
    left, right, ok = _as_floats(actual, expected)
    if not ok:
        return False
    if op is FilterOp.GT:
        return left > right
    if op is FilterOp.GTE:
        return left >= right
    if op is FilterOp.LT:
        return left < right
    return left <= right


def _as_floats(actual: Any, expected: str) -> tuple[float, float, bool]:
    try:
        return float(actual), float(expected), True
    except (TypeError, ValueError):
        return 0.0, 0.0, False


def _group_and_aggregate(
    rows: list[dict[str, Any]], compiled: CompiledQuery
) -> list[dict[str, Any]]:
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(dim) for dim in compiled.dimensions)
        buckets.setdefault(key, []).append(row)
    output: list[dict[str, Any]] = []
    for key, bucket in buckets.items():
        entry: dict[str, Any] = dict(zip(compiled.dimensions, key, strict=True))
        for measure in compiled.measures:
            alias = f"{measure.aggregation.value}_{measure.column}"
            entry[alias] = _apply_aggregation(bucket, measure.column, measure.aggregation)
        output.append(entry)
    return output


def _aggregate_all(rows: list[dict[str, Any]], compiled: CompiledQuery) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    for measure in compiled.measures:
        alias = f"{measure.aggregation.value}_{measure.column}"
        entry[alias] = _apply_aggregation(rows, measure.column, measure.aggregation)
    return entry


def _apply_aggregation(rows: list[dict[str, Any]], column: str, aggregation: Aggregation) -> Any:
    if aggregation is Aggregation.COUNT:
        return len(rows)
    numbers = [float(r[column]) for r in rows if isinstance(r.get(column), (int, float))]
    if not numbers:
        return 0
    if aggregation is Aggregation.SUM:
        return sum(numbers)
    if aggregation is Aggregation.AVG:
        return sum(numbers) / len(numbers)
    if aggregation is Aggregation.MIN:
        return min(numbers)
    return max(numbers)
