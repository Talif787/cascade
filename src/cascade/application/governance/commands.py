from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RegisterSloCommand:
    name: str
    asset_kind: str
    asset_id: str
    max_staleness_minutes: int
    severity: str = "medium"
    owner: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class ChangeFreshnessTargetCommand:
    slo_id: str
    max_staleness_minutes: int


@dataclass(frozen=True, slots=True)
class RecordCostCommand:
    asset_kind: str
    asset_id: str
    category: str
    amount_cents: int
    period_start: datetime
    period_end: datetime
    currency: str = "USD"
    source: str = "manual"


@dataclass(frozen=True, slots=True)
class ImportCostsCommand:
    window_start: datetime
    window_end: datetime
