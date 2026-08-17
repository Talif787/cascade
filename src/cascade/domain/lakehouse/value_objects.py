from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from cascade.domain.lakehouse.errors import (
    InvalidDatasetId,
    InvalidDatasetName,
    InvalidQualityCheck,
    InvalidSchedule,
    InvalidTransformation,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$")
_MAX_NAME_LEN = 127
_MAX_IDENTIFIER_LEN = 255


@dataclass(frozen=True, slots=True)
class DatasetId:
    value: uuid.UUID

    @staticmethod
    def new() -> DatasetId:
        return DatasetId(uuid.uuid4())

    @staticmethod
    def from_string(raw: str) -> DatasetId:
        try:
            return DatasetId(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidDatasetId(str(raw)) from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class DatasetName:
    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or len(self.value) > _MAX_NAME_LEN
            or not _NAME_PATTERN.match(self.value)
        ):
            raise InvalidDatasetName(str(self.value))

    def __str__(self) -> str:
        return self.value


class MedallionLayer(StrEnum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class _LayerOrder(IntEnum):
    BRONZE = 0
    SILVER = 1
    GOLD = 2


def layer_rank(layer: MedallionLayer) -> int:
    return int(_LayerOrder[layer.name])


class TransformationEngine(StrEnum):
    DBT = "dbt"
    SQL = "sql"


class Materialization(StrEnum):
    TABLE = "table"
    VIEW = "view"
    INCREMENTAL = "incremental"


class DatasetStatus(StrEnum):
    REGISTERED = "registered"
    MATERIALIZING = "materializing"
    MATERIALIZED = "materialized"
    STALE = "stale"
    FAILED = "failed"
    DEPRECATED = "deprecated"


class QualityStatus(StrEnum):
    UNKNOWN = "unknown"
    PASSED = "passed"
    FAILED = "failed"


class QualityCheckKind(StrEnum):
    NOT_NULL = "not_null"
    UNIQUE = "unique"
    ACCEPTED_VALUES = "accepted_values"
    ROW_COUNT_MIN = "row_count_min"
    FRESHNESS = "freshness"


@dataclass(frozen=True, slots=True)
class Transformation:
    engine: TransformationEngine
    identifier: str
    materialization: Materialization = Materialization.TABLE

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise InvalidTransformation("transformation identifier is required")
        if len(self.identifier) > _MAX_IDENTIFIER_LEN:
            raise InvalidTransformation("transformation identifier is too long")


@dataclass(frozen=True, slots=True)
class Schedule:
    cron: str
    timezone: str = "UTC"
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.cron, str) or len(self.cron.split()) != 5:
            raise InvalidSchedule("cron expression must have five fields")
        if not isinstance(self.timezone, str) or not self.timezone.strip():
            raise InvalidSchedule("timezone is required")


@dataclass(frozen=True, slots=True)
class QualityCheck:
    kind: QualityCheckKind
    column: str | None = None
    threshold: int | None = None
    accepted_values: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.kind in (QualityCheckKind.NOT_NULL, QualityCheckKind.UNIQUE):
            if not self.column:
                raise InvalidQualityCheck(f"{self.kind.value} requires a column")
        elif self.kind is QualityCheckKind.ACCEPTED_VALUES:
            if not self.column or not self.accepted_values:
                raise InvalidQualityCheck("accepted_values requires a column and a set of values")
        elif self.kind is QualityCheckKind.ROW_COUNT_MIN:
            if self.threshold is None or self.threshold < 0:
                raise InvalidQualityCheck("row_count_min requires a non-negative threshold")
        elif self.kind is QualityCheckKind.FRESHNESS and (
            self.threshold is None or self.threshold <= 0
        ):
            raise InvalidQualityCheck("freshness requires a positive threshold in minutes")

    @property
    def name(self) -> str:
        return f"{self.kind.value}:{self.column}" if self.column else self.kind.value


@dataclass(frozen=True, slots=True)
class QualityOutcome:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class DatasetRef:
    dataset_id: DatasetId
    name: DatasetName
    layer: MedallionLayer
