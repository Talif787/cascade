from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient

_DATASETS = "/api/v1/datasets"
_VIEWS = "/api/v1/serving-views"
_GOV = "/api/v1/governance"


async def _dataset(
    client: AsyncClient, name: str, layer: str, upstreams: list[str] | None = None
) -> dict[str, Any]:
    response = await client.post(
        _DATASETS,
        json={
            "name": name,
            "layer": layer,
            "transformation": {"engine": "dbt", "identifier": name.replace(".", "_")},
            "upstream_ids": upstreams or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _serving_view(
    client: AsyncClient, source_id: str, name: str = "analytics.orders"
) -> dict[str, Any]:
    response = await client.post(
        _VIEWS,
        json={
            "name": name,
            "source_dataset_id": source_id,
            "engine": "merge_tree",
            "columns": [{"name": "region", "type": "string", "role": "dimension"}],
            "order_by": ["region"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _slo_payload(asset_kind: str, asset_id: str, minutes: int = 1440) -> dict[str, Any]:
    return {
        "name": "orders-freshness",
        "asset_kind": asset_kind,
        "asset_id": asset_id,
        "max_staleness_minutes": minutes,
        "severity": "high",
    }


async def test_register_slo_on_dataset(client: AsyncClient) -> None:
    ds = await _dataset(client, "gold.orders", "gold")
    response = await client.post(f"{_GOV}/slos", json=_slo_payload("dataset", ds["id"]))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["state"] == "unknown"


async def test_slo_on_non_refreshable_asset_is_unprocessable(client: AsyncClient) -> None:
    # a pipeline is not a refreshable asset; also it must exist, so this is 422 either way
    response = await client.post(
        f"{_GOV}/slos",
        json=_slo_payload("pipeline", "9b3c9215-e635-4d07-a379-ca21864ebddb"),
    )
    assert response.status_code == 422


async def test_slo_on_unknown_dataset_is_unprocessable(client: AsyncClient) -> None:
    response = await client.post(
        f"{_GOV}/slos",
        json=_slo_payload("dataset", "9b3c9215-e635-4d07-a379-ca21864ebddb"),
    )
    assert response.status_code == 422


async def test_evaluate_slo_breached_when_never_materialized(client: AsyncClient) -> None:
    ds = await _dataset(client, "gold.orders", "gold")
    slo = (await client.post(f"{_GOV}/slos", json=_slo_payload("dataset", ds["id"]))).json()
    response = await client.post(f"{_GOV}/slos/{slo['id']}/evaluate")
    body = response.json()
    assert body["state"] == "breached"
    assert body["breach_count"] == 1


async def test_evaluate_slo_meeting_after_materialize(client: AsyncClient) -> None:
    ds = await _dataset(client, "gold.orders", "gold")
    await client.post(f"{_DATASETS}/{ds['id']}/materialize")
    slo = (await client.post(f"{_GOV}/slos", json=_slo_payload("dataset", ds["id"]))).json()
    response = await client.post(f"{_GOV}/slos/{slo['id']}/evaluate")
    assert response.json()["state"] == "meeting"


async def test_evaluate_all_active(client: AsyncClient) -> None:
    ds = await _dataset(client, "gold.orders", "gold")
    await client.post(f"{_GOV}/slos", json=_slo_payload("dataset", ds["id"]))
    response = await client.post(f"{_GOV}/slos/evaluate")
    assert response.status_code == 200
    assert len(response.json()["evaluated"]) == 1


async def test_slo_lifecycle(client: AsyncClient) -> None:
    ds = await _dataset(client, "gold.orders", "gold")
    slo = (await client.post(f"{_GOV}/slos", json=_slo_payload("dataset", ds["id"]))).json()
    assert (await client.post(f"{_GOV}/slos/{slo['id']}/suspend")).json()["status"] == "suspended"
    assert (await client.post(f"{_GOV}/slos/{slo['id']}/resume")).json()["status"] == "active"
    assert (await client.post(f"{_GOV}/slos/{slo['id']}/retire")).json()["status"] == "retired"


async def test_change_target(client: AsyncClient) -> None:
    ds = await _dataset(client, "gold.orders", "gold")
    slo = (await client.post(f"{_GOV}/slos", json=_slo_payload("dataset", ds["id"]))).json()
    response = await client.put(
        f"{_GOV}/slos/{slo['id']}/target", json={"max_staleness_minutes": 30}
    )
    assert response.json()["max_staleness_minutes"] == 30


async def test_list_slos_filter_by_asset_kind(client: AsyncClient) -> None:
    ds = await _dataset(client, "gold.orders", "gold")
    await client.post(f"{_GOV}/slos", json=_slo_payload("dataset", ds["id"]))
    response = await client.get(f"{_GOV}/slos", params={"asset_kind": "dataset"})
    assert response.json()["meta"]["total"] == 1


async def test_record_cost_and_report(client: AsyncClient) -> None:
    ds = await _dataset(client, "gold.orders", "gold")
    now = datetime.now(UTC)
    payload = {
        "asset_kind": "dataset",
        "asset_id": ds["id"],
        "category": "compute",
        "amount_cents": 5000,
        "period_start": (now - timedelta(days=1)).isoformat(),
        "period_end": now.isoformat(),
    }
    created = await client.post(f"{_GOV}/costs", json=payload)
    assert created.status_code == 201

    report = await client.get(f"{_GOV}/costs/report")
    body = report.json()
    assert body["total_cents"] == 5000
    assert any(line["key"] == "compute" for line in body["by_category"])


async def test_record_cost_unknown_asset_is_unprocessable(client: AsyncClient) -> None:
    now = datetime.now(UTC)
    response = await client.post(
        f"{_GOV}/costs",
        json={
            "asset_kind": "dataset",
            "asset_id": "9b3c9215-e635-4d07-a379-ca21864ebddb",
            "category": "compute",
            "amount_cents": 100,
            "period_start": (now - timedelta(days=1)).isoformat(),
            "period_end": now.isoformat(),
        },
    )
    assert response.status_code == 422


async def test_lineage_across_datasets_and_serving_view(client: AsyncClient) -> None:
    bronze = await _dataset(client, "bronze.orders", "bronze")
    silver = await _dataset(client, "silver.orders", "silver", upstreams=[bronze["id"]])
    gold = await _dataset(client, "gold.orders", "gold", upstreams=[silver["id"]])
    view = await _serving_view(client, gold["id"])

    response = await client.get(f"{_GOV}/lineage/dataset/{silver['id']}")
    assert response.status_code == 200
    body = response.json()
    node_ids = {n["id"] for n in body["nodes"]}
    # upstream bronze, self silver, downstream gold, and the serving view on gold
    assert bronze["id"] in node_ids
    assert silver["id"] in node_ids
    assert gold["id"] in node_ids
    assert view["id"] in node_ids


async def test_lineage_unknown_asset_is_not_found(client: AsyncClient) -> None:
    response = await client.get(f"{_GOV}/lineage/dataset/9b3c9215-e635-4d07-a379-ca21864ebddb")
    assert response.status_code == 404


async def test_missing_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get(f"{_GOV}/slos", headers={"Authorization": ""})
    assert response.status_code == 401


async def test_readonly_cannot_register_slo(readonly_client: AsyncClient) -> None:
    response = await readonly_client.post(
        f"{_GOV}/slos",
        json=_slo_payload("dataset", "9b3c9215-e635-4d07-a379-ca21864ebddb"),
    )
    assert response.status_code == 403
