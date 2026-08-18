from __future__ import annotations

from typing import Any

from cascade.domain.copilot.aggregate import CopilotQuery
from cascade.domain.copilot.value_objects import (
    CopilotQueryId,
    CopilotStatus,
    Question,
    TranslatedFilter,
    TranslatedMeasure,
    TranslatedQuery,
)
from cascade.infrastructure.database.models import CopilotQueryModel


def _translated_to_dict(translated: TranslatedQuery) -> dict[str, Any]:
    return {
        "dimensions": list(translated.dimensions),
        "measures": [
            {"column": m.column, "aggregation": m.aggregation} for m in translated.measures
        ],
        "filters": [
            {"column": f.column, "op": f.op, "values": list(f.values)} for f in translated.filters
        ],
        "limit": translated.limit,
    }


def _translated_from_dict(payload: dict[str, Any]) -> TranslatedQuery:
    return TranslatedQuery(
        dimensions=tuple(payload.get("dimensions", [])),
        measures=tuple(
            TranslatedMeasure(column=m["column"], aggregation=m["aggregation"])
            for m in payload.get("measures", [])
        ),
        filters=tuple(
            TranslatedFilter(column=f["column"], op=f["op"], values=tuple(f.get("values", [])))
            for f in payload.get("filters", [])
        ),
        limit=int(payload.get("limit", 100)),
    )


def copilot_query_to_model(query: CopilotQuery) -> CopilotQueryModel:
    translated = query.translated
    return CopilotQueryModel(
        id=query.id.value,
        question=str(query.question),
        view_id=query.view_id,
        view_name=query.view_name,
        status=query.status.value,
        translated=_translated_to_dict(translated) if translated is not None else None,
        rejection_reason=query.rejection_reason,
        row_count=query.row_count,
        version=query.version,
        created_at=query.created_at,
        updated_at=query.updated_at,
    )


def model_to_copilot_query(model: CopilotQueryModel) -> CopilotQuery:
    translated = _translated_from_dict(model.translated) if model.translated is not None else None
    return CopilotQuery(
        CopilotQueryId(model.id),
        question=Question(model.question),
        view_id=model.view_id,
        view_name=model.view_name,
        status=CopilotStatus(model.status),
        translated=translated,
        rejection_reason=model.rejection_reason,
        row_count=model.row_count,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )
