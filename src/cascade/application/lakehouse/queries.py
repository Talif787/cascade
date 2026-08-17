from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetDatasetQuery:
    dataset_id: str


@dataclass(frozen=True, slots=True)
class GetLineageQuery:
    dataset_id: str


@dataclass(frozen=True, slots=True)
class ListDatasetsQuery:
    layer: str | None = None
    status: str | None = None
    quality_status: str | None = None
    contract_id: str | None = None
    page: int = 1
    size: int = 20
    sort_by: str = "created_at"
    descending: bool = True
