from __future__ import annotations

from typing import Any

from httpx import AsyncClient

_BASE = "/api/v1/contracts"


def _schema(*fields: dict[str, Any]) -> dict[str, Any]:
    return {"fields": list(fields)}


def _field(name: str, type_: str, **kwargs: Any) -> dict[str, Any]:
    return {"name": name, "type": type_, **kwargs}


def _register_payload(name: str = "orders-value") -> dict[str, Any]:
    return {
        "name": name,
        "schema_format": "avro",
        "compatibility_mode": "backward",
        "schema": _schema(_field("id", "long"), _field("amount", "double")),
        "description": "order events",
    }


async def test_register_contract_returns_created(client: AsyncClient) -> None:
    response = await client.post(_BASE, json=_register_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "orders-value"
    assert body["latest_version"] == 1
    assert body["schema_versions"][0]["registry_id"] is not None


async def test_publish_compatible_version(client: AsyncClient) -> None:
    contract = (await client.post(_BASE, json=_register_payload())).json()
    response = await client.post(
        f"{_BASE}/{contract['id']}/versions",
        json={
            "schema": _schema(
                _field("id", "long"),
                _field("amount", "double"),
                _field("currency", "string", has_default=True),
            )
        },
    )
    assert response.status_code == 201
    assert response.json()["version"] == 2


async def test_publish_incompatible_version_conflicts(client: AsyncClient) -> None:
    contract = (await client.post(_BASE, json=_register_payload())).json()
    response = await client.post(
        f"{_BASE}/{contract['id']}/versions",
        json={
            "schema": _schema(
                _field("id", "long"),
                _field("amount", "double"),
                _field("currency", "string"),
            )
        },
    )
    assert response.status_code == 409
    body = response.json()
    assert body["compatibility_mode"] == "backward"
    assert body["violations"]


async def test_compatibility_dry_run_does_not_publish(client: AsyncClient) -> None:
    contract = (await client.post(_BASE, json=_register_payload())).json()
    response = await client.post(
        f"{_BASE}/{contract['id']}/compatibility",
        json={
            "schema": _schema(_field("id", "long"), _field("amount", "double"), _field("x", "int"))
        },
    )
    assert response.status_code == 200
    assert response.json()["compatible"] is False

    fetched = (await client.get(f"{_BASE}/{contract['id']}")).json()
    assert fetched["latest_version"] == 1


async def test_get_version(client: AsyncClient) -> None:
    contract = (await client.post(_BASE, json=_register_payload())).json()
    response = await client.get(f"{_BASE}/{contract['id']}/versions/1")
    assert response.status_code == 200
    assert response.json()["version"] == 1


async def test_change_compatibility_mode(client: AsyncClient) -> None:
    contract = (await client.post(_BASE, json=_register_payload())).json()
    response = await client.put(
        f"{_BASE}/{contract['id']}/compatibility-mode",
        json={"compatibility_mode": "full"},
    )
    assert response.status_code == 200
    assert response.json()["compatibility_mode"] == "full"


async def test_deprecate_version(client: AsyncClient) -> None:
    contract = (await client.post(_BASE, json=_register_payload())).json()
    await client.post(
        f"{_BASE}/{contract['id']}/versions",
        json={
            "schema": _schema(
                _field("id", "long"),
                _field("amount", "double"),
                _field("currency", "string", has_default=True),
            )
        },
    )
    response = await client.post(f"{_BASE}/{contract['id']}/versions/1/deprecate")
    assert response.status_code == 200
    versions = {v["version"]: v for v in response.json()["schema_versions"]}
    assert versions[1]["status"] == "deprecated"


async def test_list_supports_pagination(client: AsyncClient) -> None:
    for index in range(3):
        await client.post(_BASE, json=_register_payload(name=f"topic-{index}"))
    page = await client.get(_BASE, params={"page": 1, "size": 2})
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 2
    assert body["meta"]["total"] == 3


async def test_duplicate_name_conflicts(client: AsyncClient) -> None:
    await client.post(_BASE, json=_register_payload())
    response = await client.post(_BASE, json=_register_payload())
    assert response.status_code == 409


async def test_invalid_field_type_is_unprocessable(client: AsyncClient) -> None:
    payload = _register_payload()
    payload["schema"]["fields"][0]["type"] = "complex128"
    response = await client.post(_BASE, json=payload)
    assert response.status_code == 422


async def test_missing_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.post(_BASE, json=_register_payload(), headers={"authorization": ""})
    assert response.status_code == 401


async def test_read_only_token_cannot_write(readonly_client: AsyncClient) -> None:
    response = await readonly_client.post(_BASE, json=_register_payload())
    assert response.status_code == 403


async def test_read_only_token_can_read(readonly_client: AsyncClient) -> None:
    response = await readonly_client.get(_BASE)
    assert response.status_code == 200
