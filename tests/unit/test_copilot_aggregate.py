from __future__ import annotations

import pytest

from cascade.domain.copilot.aggregate import CopilotQuery
from cascade.domain.copilot.errors import InvalidCopilotTransition
from cascade.domain.copilot.events import (
    QueryExecuted,
    QueryTranslated,
    QuestionAsked,
    TranslationRejected,
)
from cascade.domain.copilot.value_objects import (
    CopilotStatus,
    Question,
    TranslatedMeasure,
    TranslatedQuery,
)


def _ask() -> CopilotQuery:
    return CopilotQuery.ask(
        question=Question("total revenue by region"),
        view_id="view-1",
        view_name="analytics.orders",
    )


def _translated() -> TranslatedQuery:
    return TranslatedQuery(
        dimensions=("region",),
        measures=(TranslatedMeasure(column="revenue", aggregation="sum"),),
    )


def test_ask_starts_in_asked_state() -> None:
    query = _ask()
    assert query.status is CopilotStatus.ASKED
    assert any(isinstance(e, QuestionAsked) for e in query.pull_events())


def test_translate_then_execute() -> None:
    query = _ask()
    query.pull_events()
    query.record_translation(_translated())
    assert query.status is CopilotStatus.TRANSLATED
    assert any(isinstance(e, QueryTranslated) for e in query.pull_events())
    query.record_execution(24)
    assert query.status is CopilotStatus.EXECUTED
    assert query.row_count == 24
    assert any(isinstance(e, QueryExecuted) for e in query.pull_events())


def test_reject_from_asked() -> None:
    query = _ask()
    query.pull_events()
    query.reject("no known column matched")
    assert query.status is CopilotStatus.REJECTED
    assert query.rejection_reason == "no known column matched"
    assert any(isinstance(e, TranslationRejected) for e in query.pull_events())


def test_cannot_execute_before_translation() -> None:
    query = _ask()
    with pytest.raises(InvalidCopilotTransition):
        query.record_execution(1)


def test_rejected_is_terminal() -> None:
    query = _ask()
    query.reject("nope")
    with pytest.raises(InvalidCopilotTransition):
        query.record_translation(_translated())


def test_fail_after_translation() -> None:
    query = _ask()
    query.record_translation(_translated())
    query.fail("runtime exploded")
    assert query.status is CopilotStatus.FAILED
    assert query.rejection_reason == "runtime exploded"


def test_translated_query_requires_selection() -> None:
    from cascade.domain.copilot.errors import InvalidTranslation

    with pytest.raises(InvalidTranslation):
        TranslatedQuery(dimensions=(), measures=())
