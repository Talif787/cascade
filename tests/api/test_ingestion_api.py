from __future__ import annotations

from typing import Any

from httpx import AsyncClient

_SOURCES = "/api/v1/sources"
_CONTRACTS = "/api/v1/contracts"


def _contract_payload(name: str = "orders-value") -> dict[str, Any]:
    return {
        "name": name,
        "schema_format": "avro",
        "compatibility_mode": "backward",
        "schema": {"fields": [{"name": "id", "type": "long"}]},
        "description": "order events",
    }


async def _make_contract(client: AsyncClient, name: str = "orders-value") -> str:
    response = await client.post(_CONTRACTS, json=_contract_payload(name))
    assert response.status_code == 201
    return response.json()["id"]


def _source_payload(contract_id: str, name: str = "orders-postgres-cdc") -> dict[str, Any]:
    return {
        "name": name,
        "connector_kind": "postgres_cdc",
        "config": {"database.hostname": "db", "table.include.list": "public.orders"},
        "contract_id": contract_id,
        "dead_letter": {"on_failure": "dead_letter", "dlq_topic": "orders.dlq", "tolerance": 0},
        "description": "orders change stream",
    }


async def test_register_source_returns_created(client: AsyncClient) -> None:
    contract_id = await _make_contract(client)
    response = await client.post(_SOURCES, json=_source_payload(contract_id))
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "orders-postgres-cdc"
    assert body["status"] == "registered"
    assert body["contract_id"] == contract_id


async def test_register_with_unknown_contract_is_unprocessable(client: AsyncClient) -> None:
    response = await client.post(
        _SOURCES,
        json=_source_payload("9b3c9215-e635-4d07-a379-ca21864ebddb"),
    )
    assert response.status_code == 422


async def test_provision_moves_source_to_running(client: AsyncClient) -> None:
    contract_id = await _make_contract(client)
    source = (await client.post(_SOURCES, json=_source_payload(contract_id))).json()
    response = await client.post(f"{_SOURCES}/{source['id']}/provision")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["runtime_ref"] is not None


async def test_pause_and_resume(client: AsyncClient) -> None:
    contract_id = await _make_contract(client)
    source = (await client.post(_SOURCES, json=_source_payload(contract_id))).json()
    await client.post(f"{_SOURCES}/{source['id']}/provision")
    paused = await client.post(f"{_SOURCES}/{source['id']}/pause")
    assert paused.json()["status"] == "paused"
    resumed = await client.post(f"{_SOURCES}/{source['id']}/resume")
    assert resumed.json()["status"] == "running"


async def test_dead_letters_report_and_halt(client: AsyncClient) -> None:
    contract_id = await _make_contract(client)
    payload = _source_payload(contract_id)
    payload["dead_letter"] = {"on_failure": "halt", "tolerance": 3}
    source = (await client.post(_SOURCES, json=payload)).json()
    await client.post(f"{_SOURCES}/{source['id']}/provision")
    response = await client.post(f"{_SOURCES}/{source['id']}/dead-letters", json={"count": 3})
    body = response.json()
    assert body["dead_letter_count"] == 3
    assert body["status"] == "failed"


async def test_decommission(client: AsyncClient) -> None:
    contract_id = await _make_contract(client)
    source = (await client.post(_SOURCES, json=_source_payload(contract_id))).json()
    response = await client.post(f"{_SOURCES}/{source['id']}/decommission")
    assert response.json()["status"] == "decommissioned"


async def test_list_filters_by_status(client: AsyncClient) -> None:
    contract_id = await _make_contract(client)
    first = (await client.post(_SOURCES, json=_source_payload(contract_id, "src-one"))).json()
    await client.post(_SOURCES, json=_source_payload(contract_id, "src-two"))
    await client.post(f"{_SOURCES}/{first['id']}/provision")

    running = await client.get(_SOURCES, params={"status": "running"})
    assert running.status_code == 200
    names = [item["name"] for item in running.json()["items"]]
    assert names == ["src-one"]


async def test_get_source(client: AsyncClient) -> None:
    contract_id = await _make_contract(client)
    source = (await client.post(_SOURCES, json=_source_payload(contract_id))).json()
    response = await client.get(f"{_SOURCES}/{source['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == source["id"]


async def test_missing_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get(_SOURCES, headers={"Authorization": ""})
    assert response.status_code == 401


async def test_readonly_cannot_register(readonly_client: AsyncClient) -> None:
    response = await readonly_client.post(
        _SOURCES,
        json=_source_payload("9b3c9215-e635-4d07-a379-ca21864ebddb"),
    )
    assert response.status_code == 403
