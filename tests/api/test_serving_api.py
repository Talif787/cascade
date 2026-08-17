from __future__ import annotations

from typing import Any

from httpx import AsyncClient

_DATASETS = "/api/v1/datasets"
_VIEWS = "/api/v1/serving-views"


async def _make_gold_dataset(client: AsyncClient, name: str = "gold.orders_daily") -> str:
    response = await client.post(
        _DATASETS,
        json={
            "name": name,
            "layer": "gold",
            "transformation": {"engine": "dbt", "identifier": name.replace(".", "_")},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _view_payload(
    source_id: str,
    *,
    name: str = "analytics.orders_daily",
    engine: str = "merge_tree",
    with_measure: bool = True,
) -> dict[str, Any]:
    columns = [
        {"name": "day", "type": "date", "role": "time"},
        {"name": "region", "type": "string", "role": "dimension"},
    ]
    if with_measure:
        columns.append({"name": "revenue", "type": "float", "role": "measure"})
    return {
        "name": name,
        "source_dataset_id": source_id,
        "engine": engine,
        "columns": columns,
        "order_by": ["day"],
        "refresh_mode": "full",
    }


async def _register(client: AsyncClient, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(_VIEWS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_register_serving_view(client: AsyncClient) -> None:
    source = await _make_gold_dataset(client)
    body = await _register(client, _view_payload(source))
    assert body["status"] == "registered"
    assert body["source_dataset_id"] == source
    assert [c["name"] for c in body["columns"]] == ["day", "region", "revenue"]


async def test_register_with_unknown_source_is_unprocessable(client: AsyncClient) -> None:
    response = await client.post(
        _VIEWS,
        json=_view_payload("9b3c9215-e635-4d07-a379-ca21864ebddb"),
    )
    assert response.status_code == 422


async def test_aggregating_engine_without_measure_is_unprocessable(
    client: AsyncClient,
) -> None:
    source = await _make_gold_dataset(client)
    response = await client.post(
        _VIEWS,
        json=_view_payload(source, engine="aggregating_merge_tree", with_measure=False),
    )
    assert response.status_code == 422


async def test_sync_moves_view_to_ready(client: AsyncClient) -> None:
    source = await _make_gold_dataset(client)
    view = await _register(client, _view_payload(source))
    response = await client.post(f"{_VIEWS}/{view['id']}/sync")
    body = response.json()
    assert body["status"] == "ready"
    assert body["last_row_count"] is not None


async def test_query_returns_grouped_aggregation(client: AsyncClient) -> None:
    source = await _make_gold_dataset(client)
    view = await _register(client, _view_payload(source))
    await client.post(f"{_VIEWS}/{view['id']}/sync")
    response = await client.post(
        f"{_VIEWS}/{view['id']}/query",
        json={
            "dimensions": ["region"],
            "measures": [{"column": "revenue", "aggregation": "sum"}],
            "limit": 100,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "region" in body["columns"]
    assert "sum_revenue" in body["columns"]
    assert body["row_count"] >= 1


async def test_query_on_unsynced_view_is_conflict(client: AsyncClient) -> None:
    source = await _make_gold_dataset(client)
    view = await _register(client, _view_payload(source))
    response = await client.post(f"{_VIEWS}/{view['id']}/query", json={"dimensions": ["region"]})
    assert response.status_code == 409


async def test_query_with_unknown_column_is_unprocessable(client: AsyncClient) -> None:
    source = await _make_gold_dataset(client)
    view = await _register(client, _view_payload(source))
    await client.post(f"{_VIEWS}/{view['id']}/sync")
    response = await client.post(f"{_VIEWS}/{view['id']}/query", json={"dimensions": ["nope"]})
    assert response.status_code == 422


async def test_catalog_lists_ready_views(client: AsyncClient) -> None:
    source = await _make_gold_dataset(client)
    view = await _register(client, _view_payload(source))
    # not in catalog until synced
    empty = await client.get(f"{_VIEWS}/catalog")
    assert empty.json()["entries"] == []
    await client.post(f"{_VIEWS}/{view['id']}/sync")
    catalog = await client.get(f"{_VIEWS}/catalog")
    entries = catalog.json()["entries"]
    assert [e["name"] for e in entries] == ["analytics.orders_daily"]
    assert [c["name"] for c in entries[0]["columns"]] == ["day", "region", "revenue"]


async def test_reconcile_marks_stale_after_source_rematerialize(
    client: AsyncClient,
) -> None:
    source = await _make_gold_dataset(client)
    view = await _register(client, _view_payload(source))
    await client.post(f"{_VIEWS}/{view['id']}/sync")
    # rematerialize the source so it is newer than the view's sync
    await client.post(f"{_DATASETS}/{source}/materialize")
    response = await client.post(f"{_VIEWS}/{view['id']}/reconcile")
    assert response.json()["status"] == "stale"


async def test_retire_view(client: AsyncClient) -> None:
    source = await _make_gold_dataset(client)
    view = await _register(client, _view_payload(source))
    response = await client.post(f"{_VIEWS}/{view['id']}/retire")
    assert response.json()["status"] == "retired"


async def test_list_filters_by_status(client: AsyncClient) -> None:
    source = await _make_gold_dataset(client)
    first = await _register(client, _view_payload(source, name="analytics.one"))
    await _register(client, _view_payload(source, name="analytics.two"))
    await client.post(f"{_VIEWS}/{first['id']}/sync")
    response = await client.get(_VIEWS, params={"status": "ready"})
    assert [item["name"] for item in response.json()["items"]] == ["analytics.one"]


async def test_missing_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get(_VIEWS, headers={"Authorization": ""})
    assert response.status_code == 401


async def test_readonly_cannot_register(readonly_client: AsyncClient) -> None:
    response = await readonly_client.post(
        _VIEWS, json=_view_payload("9b3c9215-e635-4d07-a379-ca21864ebddb")
    )
    assert response.status_code == 403
