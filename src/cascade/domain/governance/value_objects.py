from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from cascade.domain.governance.errors import (
    InvalidAssetRef,
    InvalidCostEntryId,
    InvalidCostPeriod,
    InvalidFreshnessTarget,
    InvalidMoney,
    InvalidSloId,
    InvalidSloName,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


class AssetKind(StrEnum):
    PIPELINE = "pipeline"
    INGESTION_SOURCE = "ingestion_source"
    STREAM_JOB = "stream_job"
    DATASET = "dataset"
    SERVING_VIEW = "serving_view"


_REFRESHABLE_KINDS = frozenset({AssetKind.DATASET, AssetKind.SERVING_VIEW})


class SloStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class ComplianceState(StrEnum):
    UNKNOWN = "unknown"
    MEETING = "meeting"
    AT_RISK = "at_risk"
    BREACHED = "breached"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CostCategory(StrEnum):
    COMPUTE = "compute"
    STORAGE = "storage"
    TRANSFER = "transfer"


@dataclass(frozen=True, slots=True)
class SloId:
    value: uuid.UUID

    @staticmethod
    def new() -> SloId:
        return SloId(uuid.uuid4())

    @staticmethod
    def from_string(raw: str) -> SloId:
        try:
            return SloId(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidSloId(str(raw)) from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class CostEntryId:
    value: uuid.UUID

    @staticmethod
    def new() -> CostEntryId:
        return CostEntryId(uuid.uuid4())

    @staticmethod
    def from_string(raw: str) -> CostEntryId:
        try:
            return CostEntryId(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidCostEntryId(str(raw)) from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class SloName:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _NAME_PATTERN.match(self.value):
            raise InvalidSloName(str(self.value))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AssetRef:
    kind: AssetKind
    asset_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise InvalidAssetRef("asset id is required")

    @property
    def is_refreshable(self) -> bool:
        return self.kind in _REFRESHABLE_KINDS

    def __str__(self) -> str:
        return f"{self.kind.value}:{self.asset_id}"


@dataclass(frozen=True, slots=True)
class FreshnessTarget:
    max_staleness_minutes: int

    def __post_init__(self) -> None:
        if not isinstance(self.max_staleness_minutes, int) or self.max_staleness_minutes <= 0:
            raise InvalidFreshnessTarget("max staleness must be a positive number of minutes")

    @property
    def warn_threshold_minutes(self) -> float:
        return self.max_staleness_minutes * 0.8


@dataclass(frozen=True, slots=True)
class Money:
    amount_cents: int
    currency: str = "USD"

    def __post_init__(self) -> None:
        if not isinstance(self.amount_cents, int) or self.amount_cents < 0:
            raise InvalidMoney("amount must be a non-negative number of cents")
        if not isinstance(self.currency, str) or len(self.currency) != 3:
            raise InvalidMoney("currency must be a three-letter code")

    def add(self, other: Money) -> Money:
        if other.currency != self.currency:
            raise InvalidMoney("cannot add amounts in different currencies")
        return Money(amount_cents=self.amount_cents + other.amount_cents, currency=self.currency)


@dataclass(frozen=True, slots=True)
class CostPeriod:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise InvalidCostPeriod("cost period start must be before its end")
