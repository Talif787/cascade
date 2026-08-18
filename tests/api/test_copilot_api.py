from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from cascade.application.copilot.translator import (
    TranslatedFilterSpec,
    TranslatedMeasureSpec,
    TranslationResult,
)

_DATASETS = "/api/v1/datasets"
_VIEWS = "/api/v1/serving-views"
_COPILOT = "/api/v1/copilot"


async def _ready_view(client: AsyncClient) -> dict[str, Any]:
    ds = await client.post(
        _DATASETS,
        json={
            "name": "gold.orders",
            "layer": "gold",
            "transformation": {"engine": "dbt", "identifier": "gold_orders"},
        },
    )
    source_id = ds.json()["id"]
    view = await client.post(
        _VIEWS,
        json={
            "name": "analytics.orders",
            "source_dataset_id": source_id,
            "engine": "merge_tree",
            "columns": [
                {"name": "region", "type": "string", "role": "dimension"},
                {"name": "revenue", "type": "float", "role": "measure"},
            ],
            "order_by": ["region"],
        },
    )
    body = view.json()
    await client.post(f"{_VIEWS}/{body['id']}/sync")
    return body


async def test_ask_executes_and_returns_rows(client: AsyncClient, translator: Any) -> None:
    await _ready_view(client)
    translator.result = TranslationResult(
        dimensions=("region",),
        measures=(TranslatedMeasureSpec(column="revenue", aggregation="sum"),),
        limit=100,
    )
    response = await client.post(
        f"{_COPILOT}/ask",
        json={"question": "total revenue by region", "view_name": "analytics.orders"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "executed"
    assert body["translated"]["dimensions"] == ["region"]
    assert "region" in body["columns"]
    assert body["row_count"] >= 1


async def test_ask_rejects_hallucinated_column(client: AsyncClient, translator: Any) -> None:
    await _ready_view(client)
    # the translator proposes a column that does not exist on the view
    translator.result = TranslationResult(dimensions=("nonexistent",))
    response = await client.post(
        f"{_COPILOT}/ask",
        json={"question": "show me the fake column", "view_name": "analytics.orders"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] is not None
    assert body["row_count"] is None


async def test_ask_without_mappable_columns_is_rejected(
    client: AsyncClient, translator: Any
) -> None:
    await _ready_view(client)
    translator.result = TranslationResult()  # empty: nothing matched
    response = await client.post(
        f"{_COPILOT}/ask",
        json={"question": "gibberish", "view_name": "analytics.orders"},
    )
    assert response.json()["status"] == "rejected"


async def test_ask_translate_only_does_not_execute(client: AsyncClient, translator: Any) -> None:
    await _ready_view(client)
    translator.result = TranslationResult(
        dimensions=("region",),
        measures=(TranslatedMeasureSpec(column="revenue", aggregation="sum"),),
    )
    response = await client.post(
        f"{_COPILOT}/ask",
        json={
            "question": "total revenue by region",
            "view_name": "analytics.orders",
            "execute": False,
        },
    )
    body = response.json()
    assert body["status"] == "translated"
    assert body["rows"] == []


async def test_ask_filter_is_carried_through(client: AsyncClient, translator: Any) -> None:
    await _ready_view(client)
    translator.result = TranslationResult(
        dimensions=("region",),
        filters=(TranslatedFilterSpec(column="region", op="eq", values=("value_0",)),),
    )
    response = await client.post(
        f"{_COPILOT}/ask",
        json={"question": "revenue for region value_0", "view_name": "analytics.orders"},
    )
    body = response.json()
    assert body["status"] == "executed"
    assert body["translated"]["filters"][0]["column"] == "region"


async def test_ask_unknown_view_is_not_found(client: AsyncClient) -> None:
    response = await client.post(
        f"{_COPILOT}/ask",
        json={"question": "anything", "view_name": "analytics.missing"},
    )
    assert response.status_code == 404


async def test_ask_without_view_is_unprocessable(client: AsyncClient) -> None:
    response = await client.post(f"{_COPILOT}/ask", json={"question": "anything"})
    assert response.status_code == 422


async def test_audit_trail_lists_and_gets(client: AsyncClient, translator: Any) -> None:
    await _ready_view(client)
    translator.result = TranslationResult(dimensions=("region",))
    ask = await client.post(
        f"{_COPILOT}/ask",
        json={
            "question": "region breakdown",
            "view_name": "analytics.orders",
            "execute": False,
        },
    )
    query_id = ask.json()["id"]

    listed = await client.get(f"{_COPILOT}/queries")
    assert listed.json()["meta"]["total"] == 1

    fetched = await client.get(f"{_COPILOT}/queries/{query_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == query_id


async def test_readonly_cannot_ask(readonly_client: AsyncClient) -> None:
    response = await readonly_client.post(
        f"{_COPILOT}/ask",
        json={"question": "anything", "view_name": "analytics.orders"},
    )
    assert response.status_code == 403
