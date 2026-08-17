from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetSourceQuery:
    source_id: str


@dataclass(frozen=True, slots=True)
class ListSourcesQuery:
    status: str | None = None
    connector_kind: str | None = None
    contract_id: str | None = None
    page: int = 1
    size: int = 20
    sort_by: str = "created_at"
    descending: bool = True
