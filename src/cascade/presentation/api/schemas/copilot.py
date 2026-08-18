from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cascade.application.copilot.dto import (
    CopilotAnswerView,
    CopilotQueryView,
    TranslatedQueryView,
)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000, examples=["total revenue by region"])
    view_id: str | None = None
    view_name: str | None = Field(default=None, examples=["analytics.orders_daily"])
    execute: bool = True


class TranslatedMeasureResponse(BaseModel):
    column: str
    aggregation: str


class TranslatedFilterResponse(BaseModel):
    column: str
    op: str
    values: list[str]


class TranslatedQueryResponse(BaseModel):
    dimensions: list[str]
    measures: list[TranslatedMeasureResponse]
    filters: list[TranslatedFilterResponse]
    limit: int

    @classmethod
    def from_view(cls, view: TranslatedQueryView) -> TranslatedQueryResponse:
        return cls(
            dimensions=view.dimensions,
            measures=[
                TranslatedMeasureResponse(column=m.column, aggregation=m.aggregation)
                for m in view.measures
            ],
            filters=[
                TranslatedFilterResponse(column=f.column, op=f.op, values=f.values)
                for f in view.filters
            ],
            limit=view.limit,
        )


class AskResponse(BaseModel):
    id: str
    question: str
    view_id: str
    view_name: str
    status: str
    translated: TranslatedQueryResponse | None
    rejection_reason: str | None
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int | None

    @classmethod
    def from_view(cls, view: CopilotAnswerView) -> AskResponse:
        return cls(
            id=view.id,
            question=view.question,
            view_id=view.view_id,
            view_name=view.view_name,
            status=view.status,
            translated=(
                TranslatedQueryResponse.from_view(view.translated)
                if view.translated is not None
                else None
            ),
            rejection_reason=view.rejection_reason,
            columns=view.columns,
            rows=view.rows,
            row_count=view.row_count,
        )


class CopilotQueryResponse(BaseModel):
    id: str
    question: str
    view_id: str
    view_name: str
    status: str
    translated: TranslatedQueryResponse | None
    rejection_reason: str | None
    row_count: int | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_view(cls, view: CopilotQueryView) -> CopilotQueryResponse:
        return cls(
            id=view.id,
            question=view.question,
            view_id=view.view_id,
            view_name=view.view_name,
            status=view.status,
            translated=(
                TranslatedQueryResponse.from_view(view.translated)
                if view.translated is not None
                else None
            ),
            rejection_reason=view.rejection_reason,
            row_count=view.row_count,
            created_at=view.created_at,
            updated_at=view.updated_at,
        )
