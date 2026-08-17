from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetServingViewQuery:
    view_id: str


@dataclass(frozen=True, slots=True)
class ListServingViewsQuery:
    status: str | None = None
    engine: str | None = None
    source_dataset_id: str | None = None
    page: int = 1
    size: int = 20
    sort_by: str = "created_at"
    descending: bool = True
