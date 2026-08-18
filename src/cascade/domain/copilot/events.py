from __future__ import annotations

from dataclasses import dataclass

from cascade.domain.common.events import DomainEvent
from cascade.domain.copilot.value_objects import CopilotQueryId


@dataclass(frozen=True, slots=True, kw_only=True)
class CopilotEvent(DomainEvent):
    query_id: CopilotQueryId


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestionAsked(CopilotEvent):
    view_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class QueryTranslated(CopilotEvent):
    dimension_count: int
    measure_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class TranslationRejected(CopilotEvent):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class QueryExecuted(CopilotEvent):
    row_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionFailed(CopilotEvent):
    reason: str
