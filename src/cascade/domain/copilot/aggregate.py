from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import AggregateRoot, utcnow
from cascade.domain.copilot.errors import InvalidCopilotTransition
from cascade.domain.copilot.events import (
    ExecutionFailed,
    QueryExecuted,
    QueryTranslated,
    QuestionAsked,
    TranslationRejected,
)
from cascade.domain.copilot.value_objects import (
    CopilotQueryId,
    CopilotStatus,
    Question,
    TranslatedQuery,
)

_MAX_REASON_LEN = 512

_ALLOWED_TRANSITIONS: dict[CopilotStatus, frozenset[CopilotStatus]] = {
    CopilotStatus.ASKED: frozenset({CopilotStatus.TRANSLATED, CopilotStatus.REJECTED}),
    CopilotStatus.TRANSLATED: frozenset({CopilotStatus.EXECUTED, CopilotStatus.FAILED}),
    CopilotStatus.REJECTED: frozenset(),
    CopilotStatus.EXECUTED: frozenset(),
    CopilotStatus.FAILED: frozenset(),
}


class CopilotQuery(AggregateRoot[CopilotQueryId]):
    """A natural-language question translated into a governed analytics query."""

    def __init__(
        self,
        query_id: CopilotQueryId,
        *,
        question: Question,
        view_id: str,
        view_name: str,
        status: CopilotStatus,
        translated: TranslatedQuery | None,
        rejection_reason: str | None,
        row_count: int | None,
        created_at: datetime,
        updated_at: datetime,
        version: int = 0,
    ) -> None:
        super().__init__(query_id, version=version)
        self._question = question
        self._view_id = view_id
        self._view_name = view_name
        self._status = status
        self._translated = translated
        self._rejection_reason = rejection_reason
        self._row_count = row_count
        self._created_at = created_at
        self._updated_at = updated_at

    @classmethod
    def ask(cls, *, question: Question, view_id: str, view_name: str) -> CopilotQuery:
        now = utcnow()
        query = cls(
            CopilotQueryId.new(),
            question=question,
            view_id=view_id,
            view_name=view_name,
            status=CopilotStatus.ASKED,
            translated=None,
            rejection_reason=None,
            row_count=None,
            created_at=now,
            updated_at=now,
        )
        query._record(QuestionAsked(query_id=query.id, view_id=view_id))
        return query

    @property
    def question(self) -> Question:
        return self._question

    @property
    def view_id(self) -> str:
        return self._view_id

    @property
    def view_name(self) -> str:
        return self._view_name

    @property
    def status(self) -> CopilotStatus:
        return self._status

    @property
    def translated(self) -> TranslatedQuery | None:
        return self._translated

    @property
    def rejection_reason(self) -> str | None:
        return self._rejection_reason

    @property
    def row_count(self) -> int | None:
        return self._row_count

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def record_translation(self, translated: TranslatedQuery) -> None:
        self._transition_to(CopilotStatus.TRANSLATED)
        self._translated = translated
        self._record(
            QueryTranslated(
                query_id=self.id,
                dimension_count=len(translated.dimensions),
                measure_count=len(translated.measures),
            )
        )

    def reject(self, reason: str) -> None:
        self._transition_to(CopilotStatus.REJECTED)
        self._rejection_reason = reason.strip()[:_MAX_REASON_LEN]
        self._record(TranslationRejected(query_id=self.id, reason=self._rejection_reason or ""))

    def record_execution(self, row_count: int) -> None:
        self._transition_to(CopilotStatus.EXECUTED)
        self._row_count = row_count
        self._record(QueryExecuted(query_id=self.id, row_count=row_count))

    def fail(self, reason: str) -> None:
        self._transition_to(CopilotStatus.FAILED)
        self._rejection_reason = reason.strip()[:_MAX_REASON_LEN]
        self._record(ExecutionFailed(query_id=self.id, reason=self._rejection_reason or ""))

    def _transition_to(self, target: CopilotStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self._status]:
            raise InvalidCopilotTransition(self._status.value, target.value)
        self._status = target
        self._updated_at = utcnow()
