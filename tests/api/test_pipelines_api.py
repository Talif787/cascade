from __future__ import annotations

from typing import Any

from httpx import AsyncClient

_BASE = "/api/v1/pipelines"


def _payload(name: str = "orders-cdc") -> dict[str, Any]:
    return {
        "name": name,
        "source": {"type": "postgres_cdc", "resource": "public.orders"},
        "sink": {"type": "iceberg", "resource": "bronze.orders"},
        "description": "demo pipeline",
    }


async def test_register_pipeline_returns_created(client: AsyncClient) -> None:
    response = await client.post(_BASE, json=_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "orders-cdc"
    assert body["status"] == "draft"
    assert body["version"] == 0
    assert body["id"]


async def test_duplicate_name_conflicts(client: AsyncClient) -> None:
    await client.post(_BASE, json=_payload())
    response = await client.post(_BASE, json=_payload())
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_invalid_connector_type_is_unprocessable(client: AsyncClient) -> None:
    payload = _payload()
    payload["source"]["type"] = "carrier-pigeon"
    response = await client.post(_BASE, json=payload)
    assert response.status_code == 422


async def test_get_missing_pipeline_returns_not_found(client: AsyncClient) -> None:
    response = await client.get(f"{_BASE}/{'0' * 8}-0000-0000-0000-000000000000")
    assert response.status_code == 404


async def test_get_invalid_id_is_unprocessable(client: AsyncClient) -> None:
    response = await client.get(f"{_BASE}/not-a-uuid")
    assert response.status_code == 422


async def test_lifecycle_activate_then_pause(client: AsyncClient) -> None:
    created = (await client.post(_BASE, json=_payload())).json()
    pipeline_id = created["id"]

    activated = await client.post(f"{_BASE}/{pipeline_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    assert activated.json()["version"] == 1

    paused = await client.post(f"{_BASE}/{pipeline_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"


async def test_invalid_transition_conflicts(client: AsyncClient) -> None:
    created = (await client.post(_BASE, json=_payload())).json()
    response = await client.post(f"{_BASE}/{created['id']}/pause")
    assert response.status_code == 409


async def test_list_supports_pagination_and_filtering(client: AsyncClient) -> None:
    for index in range(3):
        await client.post(_BASE, json=_payload(name=f"pipeline-{index}"))
    activate_target = (await client.post(_BASE, json=_payload(name="to-activate"))).json()
    await client.post(f"{_BASE}/{activate_target['id']}/activate")

    page = await client.get(_BASE, params={"page": 1, "size": 2})
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 2
    assert body["meta"]["total"] == 4
    assert body["meta"]["pages"] == 2

    active = await client.get(_BASE, params={"status": "active"})
    assert active.json()["meta"]["total"] == 1


async def test_idempotent_registration_replays_response(client: AsyncClient) -> None:
    headers = {"Idempotency-Key": "abc-123"}
    first = await client.post(_BASE, json=_payload(), headers=headers)
    second = await client.post(_BASE, json=_payload(), headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_missing_bearer_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.post(_BASE, json=_payload(), headers={"authorization": ""})
    assert response.status_code == 401
