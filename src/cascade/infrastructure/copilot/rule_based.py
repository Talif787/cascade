from __future__ import annotations

import re
from collections.abc import Sequence

from cascade.application.copilot.translator import (
    Nl2SqlTranslator,
    TranslatedFilterSpec,
    TranslatedMeasureSpec,
    TranslationColumn,
    TranslationResult,
    TranslationSchema,
)

_AGGREGATION_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("average", "avg", "mean"), "avg"),
    (("total", "sum"), "sum"),
    (("maximum", "max", "highest", "largest", "peak"), "max"),
    (("minimum", "min", "lowest", "smallest"), "min"),
    (("count", "number of", "how many"), "count"),
)

_GROUP_MARKERS = ("by", "per", "for each", "across", "grouped by")

_PREVIEW_MARKERS = ("show", "list", "preview", "sample", "display", "browse")

_FILTER_PATTERN = "{col}\\s+(?:is|=|equals|equal to)\\s+([a-z0-9_.-]+)"

_TOP_PATTERN = re.compile(r"\b(?:top|first|limit)\s+(\d{1,5})\b")


class RuleBasedTranslator(Nl2SqlTranslator):
    """A deterministic translator that maps questions to declared columns.

    It never invents columns: it only proposes names that appear in the schema,
    so the application layer's validation is a second guard rather than the only
    one. It handles aggregations, group-by dimensions, simple equality filters,
    and a row limit, and falls back to a dimension preview for browse-style
    questions.
    """

    async def translate(self, question: str, schema: TranslationSchema) -> TranslationResult:
        text = question.lower()
        normalized = re.sub(r"[_\s]+", " ", text)

        dimensions = [c for c in schema.columns if c.role in ("dimension", "time")]
        measures = [c for c in schema.columns if c.role == "measure"]

        mentioned_dimensions = _mentioned(dimensions, normalized)
        mentioned_measures = _mentioned(measures, normalized)
        aggregation = _detect_aggregation(normalized)

        selected_dimensions = _detect_group_by(dimensions, normalized)
        for name in mentioned_dimensions:
            if name not in selected_dimensions:
                selected_dimensions.append(name)

        selected_measures: list[TranslatedMeasureSpec] = []
        agg = aggregation or "sum"
        for name in mentioned_measures:
            selected_measures.append(TranslatedMeasureSpec(column=name, aggregation=agg))
        if aggregation == "count" and not selected_measures and measures:
            selected_measures.append(
                TranslatedMeasureSpec(column=measures[0].name, aggregation="count")
            )

        filters = _detect_filters(schema, normalized)
        limit = _detect_limit(normalized)

        if not selected_dimensions and not selected_measures:
            if any(marker in normalized for marker in _PREVIEW_MARKERS) and dimensions:
                selected_dimensions = [c.name for c in dimensions]
            else:
                return TranslationResult(notes="no known column matched the question")

        return TranslationResult(
            dimensions=tuple(selected_dimensions),
            measures=tuple(selected_measures),
            filters=filters,
            limit=limit,
            notes="translated by rule-based engine",
        )


def _mentioned(columns: Sequence[TranslationColumn], normalized: str) -> list[str]:
    result: list[str] = []
    for column in columns:
        spaced = column.name.replace("_", " ")
        if re.search(rf"\b{re.escape(spaced)}\b", normalized):
            result.append(column.name)
    return result


def _detect_aggregation(normalized: str) -> str | None:
    for keywords, aggregation in _AGGREGATION_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return aggregation
    return None


def _detect_group_by(columns: Sequence[TranslationColumn], normalized: str) -> list[str]:
    selected: list[str] = []
    for column in columns:
        spaced = column.name.replace("_", " ")
        for marker in _GROUP_MARKERS:
            matched = re.search(rf"\b{marker}\s+{re.escape(spaced)}\b", normalized)
            if matched is not None and column.name not in selected:
                selected.append(column.name)
    return selected


def _detect_filters(schema: TranslationSchema, normalized: str) -> tuple[TranslatedFilterSpec, ...]:
    filters: list[TranslatedFilterSpec] = []
    for column in schema.columns:
        spaced = column.name.replace("_", " ")
        pattern = _FILTER_PATTERN.format(col=re.escape(spaced))
        match = re.search(pattern, normalized)
        if match is not None:
            filters.append(
                TranslatedFilterSpec(column=column.name, op="eq", values=(match.group(1),))
            )
    return tuple(filters)


def _detect_limit(normalized: str) -> int:
    match = _TOP_PATTERN.search(normalized)
    if match is not None:
        return max(1, min(int(match.group(1)), 10_000))
    return 100
