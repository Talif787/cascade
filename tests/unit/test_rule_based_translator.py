from __future__ import annotations

import pytest

from cascade.application.copilot.translator import TranslationColumn, TranslationSchema
from cascade.infrastructure.copilot.rule_based import RuleBasedTranslator

pytestmark = pytest.mark.asyncio


def _schema() -> TranslationSchema:
    return TranslationSchema(
        view_name="analytics.orders",
        columns=(
            TranslationColumn(name="day", role="time", type="date"),
            TranslationColumn(name="region", role="dimension", type="string"),
            TranslationColumn(name="revenue", role="measure", type="float"),
            TranslationColumn(name="order_count", role="measure", type="int"),
        ),
    )


async def test_sum_measure_grouped_by_dimension() -> None:
    result = await RuleBasedTranslator().translate("total revenue by region", _schema())
    assert result.dimensions == ("region",)
    assert len(result.measures) == 1
    assert result.measures[0].column == "revenue"
    assert result.measures[0].aggregation == "sum"


async def test_average_aggregation_detected() -> None:
    result = await RuleBasedTranslator().translate("average revenue by region", _schema())
    assert result.measures[0].aggregation == "avg"


async def test_multi_word_column_matched() -> None:
    # "order count" should match the column "order_count"
    result = await RuleBasedTranslator().translate("total order count by region", _schema())
    columns = {m.column for m in result.measures}
    assert "order_count" in columns


async def test_equality_filter_detected() -> None:
    result = await RuleBasedTranslator().translate(
        "total revenue by region where region is north", _schema()
    )
    assert len(result.filters) == 1
    assert result.filters[0].column == "region"
    assert result.filters[0].op == "eq"
    assert result.filters[0].values == ("north",)


async def test_top_n_sets_limit() -> None:
    result = await RuleBasedTranslator().translate("top 5 revenue by region", _schema())
    assert result.limit == 5


async def test_preview_fallback_lists_dimensions() -> None:
    result = await RuleBasedTranslator().translate("show me the data", _schema())
    assert set(result.dimensions) == {"day", "region"}
    assert result.measures == ()


async def test_unmappable_question_returns_empty() -> None:
    result = await RuleBasedTranslator().translate("what is the meaning of life", _schema())
    assert result.dimensions == ()
    assert result.measures == ()


async def test_count_uses_a_measure_column() -> None:
    result = await RuleBasedTranslator().translate("how many by region", _schema())
    # count falls back to the first measure column so it is a valid aggregation
    assert result.dimensions == ("region",)
    assert result.measures
    assert result.measures[0].aggregation == "count"
