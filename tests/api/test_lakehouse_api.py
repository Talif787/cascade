from __future__ import annotations

from typing import Any

from httpx import AsyncClient

_DATASETS = "/api/v1/datasets"


def _payload(
    name: str,
    layer: str,
    *,
    upstreams: list[str] | None = None,
    quality: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "layer": layer,
        "transformation": {"engine": "dbt", "identifier": name.replace(".", "_")},
        "schedule": {"cron": "0 2 * * *", "enabled": True},
        "upstream_ids": upstreams or [],
        "quality_checks": quality or [],
    }


async def _register(client: AsyncClient, payload: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(_DATASETS, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_register_bronze_dataset(client: AsyncClient) -> None:
    body = await _register(client, _payload("bronze.orders", "bronze"))
    assert body["layer"] == "bronze"
    assert body["status"] == "registered"
    assert body["quality_status"] == "unknown"


async def test_register_silver_with_bronze_upstream(client: AsyncClient) -> None:
    bronze = await _register(client, _payload("bronze.orders", "bronze"))
    body = await _register(client, _payload("silver.orders", "silver", upstreams=[bronze["id"]]))
    assert [u["id"] for u in body["upstreams"]] == [bronze["id"]]


async def test_silver_depending_on_gold_is_rejected(client: AsyncClient) -> None:
    gold = await _register(client, _payload("gold.summary", "gold"))
    response = await client.post(
        _DATASETS, json=_payload("silver.bad", "silver", upstreams=[gold["id"]])
    )
    assert response.status_code == 422


async def test_unknown_upstream_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        _DATASETS,
        json=_payload("silver.bad", "silver", upstreams=["9b3c9215-e635-4d07-a379-ca21864ebddb"]),
    )
    assert response.status_code == 422


async def test_materialize_success_marks_materialized(client: AsyncClient) -> None:
    dataset = await _register(
        client,
        _payload(
            "silver.orders",
            "silver",
            quality=[{"kind": "not_null", "column": "id"}],
        ),
    )
    response = await client.post(f"{_DATASETS}/{dataset['id']}/materialize")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "materialized"
    assert body["quality_status"] == "passed"
    assert body["last_row_count"] is not None


async def test_materialize_failing_quality_marks_failed(client: AsyncClient) -> None:
    dataset = await _register(
        client,
        _payload(
            "silver.dirty",
            "silver",
            quality=[{"kind": "not_null", "column": "force_fail"}],
        ),
    )
    response = await client.post(f"{_DATASETS}/{dataset['id']}/materialize")
    body = response.json()
    assert body["status"] == "failed"
    assert body["quality_status"] == "failed"


async def test_materialize_marks_downstream_stale(client: AsyncClient) -> None:
    bronze = await _register(client, _payload("bronze.orders", "bronze"))
    silver = await _register(client, _payload("silver.orders", "silver", upstreams=[bronze["id"]]))
    # materialize silver so it is in the materialized state
    await client.post(f"{_DATASETS}/{silver['id']}/materialize")
    # rematerialize bronze; silver depends on it and should go stale
    await client.post(f"{_DATASETS}/{bronze['id']}/materialize")
    refreshed = await client.get(f"{_DATASETS}/{silver['id']}")
    assert refreshed.json()["status"] == "stale"


async def test_lineage_reports_upstream_and_downstream(client: AsyncClient) -> None:
    bronze = await _register(client, _payload("bronze.orders", "bronze"))
    silver = await _register(client, _payload("silver.orders", "silver", upstreams=[bronze["id"]]))
    lineage = await client.get(f"{_DATASETS}/{bronze['id']}/lineage")
    body = lineage.json()
    assert body["upstreams"] == []
    assert [d["id"] for d in body["downstreams"]] == [silver["id"]]

    silver_lineage = (await client.get(f"{_DATASETS}/{silver['id']}/lineage")).json()
    assert [u["id"] for u in silver_lineage["upstreams"]] == [bronze["id"]]


async def test_change_schedule(client: AsyncClient) -> None:
    dataset = await _register(client, _payload("silver.orders", "silver"))
    response = await client.put(
        f"{_DATASETS}/{dataset['id']}/schedule",
        json={"schedule": {"cron": "*/30 * * * *", "enabled": False}},
    )
    body = response.json()
    assert body["schedule"]["cron"] == "*/30 * * * *"
    assert body["schedule"]["enabled"] is False


async def test_deprecate_dataset(client: AsyncClient) -> None:
    dataset = await _register(client, _payload("silver.orders", "silver"))
    response = await client.post(f"{_DATASETS}/{dataset['id']}/deprecate")
    assert response.json()["status"] == "deprecated"


async def test_list_filters_by_layer(client: AsyncClient) -> None:
    await _register(client, _payload("bronze.orders", "bronze"))
    await _register(client, _payload("silver.orders", "silver"))
    response = await client.get(_DATASETS, params={"layer": "bronze"})
    names = [item["name"] for item in response.json()["items"]]
    assert names == ["bronze.orders"]


async def test_missing_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get(_DATASETS, headers={"Authorization": ""})
    assert response.status_code == 401


async def test_readonly_cannot_register(readonly_client: AsyncClient) -> None:
    response = await readonly_client.post(_DATASETS, json=_payload("silver.x", "silver"))
    assert response.status_code == 403
