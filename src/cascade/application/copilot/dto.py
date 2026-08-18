from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cascade.domain.copilot.aggregate import CopilotQuery
from cascade.domain.copilot.value_objects import TranslatedQuery


@dataclass(frozen=True, slots=True)
class TranslatedMeasureView:
    column: str
    aggregation: str


@dataclass(frozen=True, slots=True)
class TranslatedFilterView:
    column: str
    op: str
    values: list[str]


@dataclass(frozen=True, slots=True)
class TranslatedQueryView:
    dimensions: list[str]
    measures: list[TranslatedMeasureView]
    filters: list[TranslatedFilterView]
    limit: int

    @classmethod
    def from_vo(cls, translated: TranslatedQuery) -> TranslatedQueryView:
        return cls(
            dimensions=list(translated.dimensions),
            measures=[
                TranslatedMeasureView(column=m.column, aggregation=m.aggregation)
                for m in translated.measures
            ],
            filters=[
                TranslatedFilterView(column=f.column, op=f.op, values=list(f.values))
                for f in translated.filters
            ],
            limit=translated.limit,
        )


@dataclass(frozen=True, slots=True)
class CopilotAnswerView:
    id: str
    question: str
    view_id: str
    view_name: str
    status: str
    translated: TranslatedQueryView | None
    rejection_reason: str | None
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int | None
    created_at: datetime

    @classmethod
    def from_aggregate(
        cls,
        query: CopilotQuery,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> CopilotAnswerView:
        translated = query.translated
        return cls(
            id=str(query.id),
            question=str(query.question),
            view_id=query.view_id,
            view_name=query.view_name,
            status=query.status.value,
            translated=(
                TranslatedQueryView.from_vo(translated) if translated is not None else None
            ),
            rejection_reason=query.rejection_reason,
            columns=columns,
            rows=rows,
            row_count=query.row_count,
            created_at=query.created_at,
        )


@dataclass(frozen=True, slots=True)
class CopilotQueryView:
    id: str
    question: str
    view_id: str
    view_name: str
    status: str
    translated: TranslatedQueryView | None
    rejection_reason: str | None
    row_count: int | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_aggregate(cls, query: CopilotQuery) -> CopilotQueryView:
        translated = query.translated
        return cls(
            id=str(query.id),
            question=str(query.question),
            view_id=query.view_id,
            view_name=query.view_name,
            status=query.status.value,
            translated=(
                TranslatedQueryView.from_vo(translated) if translated is not None else None
            ),
            rejection_reason=query.rejection_reason,
            row_count=query.row_count,
            created_at=query.created_at,
            updated_at=query.updated_at,
        )
