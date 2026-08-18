from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class GetSloQuery:
    slo_id: str


@dataclass(frozen=True, slots=True)
class ListSlosQuery:
    asset_kind: str | None = None
    status: str | None = None
    state: str | None = None
    page: int = 1
    size: int = 20
    sort_by: str = "created_at"
    descending: bool = True


@dataclass(frozen=True, slots=True)
class GetLineageQuery:
    asset_kind: str
    asset_id: str


@dataclass(frozen=True, slots=True)
class CostReportQuery:
    window_start: datetime | None = None
    window_end: datetime | None = None
