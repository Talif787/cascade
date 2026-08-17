from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from cascade.domain.serving.errors import (
    InvalidColumn,
    InvalidExposedSchema,
    InvalidQuery,
    InvalidServingViewId,
    InvalidServingViewName,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$")
_COLUMN_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_MAX_NAME_LEN = 127


@dataclass(frozen=True, slots=True)
class ServingViewId:
    value: uuid.UUID

    @staticmethod
    def new() -> ServingViewId:
        return ServingViewId(uuid.uuid4())

    @staticmethod
    def from_string(raw: str) -> ServingViewId:
        try:
            return ServingViewId(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidServingViewId(str(raw)) from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class ServingViewName:
    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or len(self.value) > _MAX_NAME_LEN
            or not _NAME_PATTERN.match(self.value)
        ):
            raise InvalidServingViewName(str(self.value))

    def __str__(self) -> str:
        return self.value


class ServingStatus(StrEnum):
    REGISTERED = "registered"
    SYNCING = "syncing"
    READY = "ready"
    STALE = "stale"
    FAILED = "failed"
    RETIRED = "retired"


class ClickHouseEngine(StrEnum):
    MERGE_TREE = "merge_tree"
    REPLACING_MERGE_TREE = "replacing_merge_tree"
    SUMMING_MERGE_TREE = "summing_merge_tree"
    AGGREGATING_MERGE_TREE = "aggregating_merge_tree"


class RefreshMode(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"
    REFRESHABLE = "refreshable"


class ColumnRole(StrEnum):
    DIMENSION = "dimension"
    MEASURE = "measure"
    TIME = "time"


class ColumnType(StrEnum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATE = "date"
    DATETIME = "datetime"


class Aggregation(StrEnum):
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"


class FilterOp(StrEnum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"


_AGGREGATING_ENGINES = frozenset(
    {ClickHouseEngine.SUMMING_MERGE_TREE, ClickHouseEngine.AGGREGATING_MERGE_TREE}
)


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type: ColumnType
    role: ColumnRole
    nullable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _COLUMN_PATTERN.match(self.name):
            raise InvalidColumn(f"invalid column name {self.name!r}")


@dataclass(frozen=True, slots=True)
class ExposedSchema:
    columns: tuple[Column, ...]
    order_by: tuple[str, ...]
    partition_by: str | None = None

    def __post_init__(self) -> None:
        if not self.columns:
            raise InvalidExposedSchema("a serving view must expose at least one column")
        names = [c.name for c in self.columns]
        if len(names) != len(set(names)):
            raise InvalidExposedSchema("column names must be unique")
        if not self.order_by:
            raise InvalidExposedSchema("an order-by key is required")
        known = set(names)
        for key in self.order_by:
            if key not in known:
                raise InvalidExposedSchema(f"order-by column {key!r} is not declared")
        if self.partition_by is not None and self.partition_by not in known:
            raise InvalidExposedSchema(f"partition-by column {self.partition_by!r} is not declared")

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)

    def has_measure(self) -> bool:
        return any(c.role is ColumnRole.MEASURE for c in self.columns)

    def requires_measure(self, engine: ClickHouseEngine) -> bool:
        return engine in _AGGREGATING_ENGINES


@dataclass(frozen=True, slots=True)
class MeasureSelection:
    column: str
    aggregation: Aggregation


@dataclass(frozen=True, slots=True)
class FilterClause:
    column: str
    op: FilterOp
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QueryRequest:
    dimensions: tuple[str, ...] = field(default_factory=tuple)
    measures: tuple[MeasureSelection, ...] = field(default_factory=tuple)
    filters: tuple[FilterClause, ...] = field(default_factory=tuple)
    limit: int = 100


@dataclass(frozen=True, slots=True)
class QueryPlan:
    table: str
    dimensions: tuple[str, ...]
    measures: tuple[MeasureSelection, ...]
    filters: tuple[FilterClause, ...]
    limit: int

    def __post_init__(self) -> None:
        if not self.dimensions and not self.measures:
            raise InvalidQuery("a query must select at least one dimension or measure")
