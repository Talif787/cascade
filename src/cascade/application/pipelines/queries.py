from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetPipelineQuery:
    pipeline_id: str


@dataclass(frozen=True, slots=True)
class ListPipelinesQuery:
    status: str | None = None
    page: int = 1
    size: int = 20
    sort_by: str = "created_at"
    descending: bool = True
