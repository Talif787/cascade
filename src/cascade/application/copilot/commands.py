from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AskCommand:
    question: str
    view_id: str | None = None
    view_name: str | None = None
    execute: bool = True


@dataclass(frozen=True, slots=True)
class GetCopilotQueryQuery:
    query_id: str


@dataclass(frozen=True, slots=True)
class ListCopilotQueriesQuery:
    status: str | None = None
    view_id: str | None = None
    page: int = 1
    size: int = 20
    descending: bool = True
