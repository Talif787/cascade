from __future__ import annotations

from typing import Any

from httpx import AsyncClient

_JOBS = "/api/v1/jobs"
_CONTRACTS = "/api/v1/contracts"


def _job_payload(
    name: str = "orders-enrichment",
    *,
    sink_kind: str = "iceberg",
    guarantee: str = "exactly_once",
    contract_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "source": {"kind": "kafka_topic", "resource": "events.orders"},
        "sink": {"kind": sink_kind, "resource": "lake.silver.orders"},
        "delivery_guarantee": guarantee,
        "checkpoint": {"interval_ms": 30_000},
        "parallelism": 2,
        "description": "enrich orders",
    }
    if contract_id is not None:
        payload["contract_id"] = contract_id
    return payload


async def _make_contract(client: AsyncClient, name: str = "orders-value") -> str:
    response = await client.post(
        _CONTRACTS,
        json={
            "name": name,
            "schema_format": "avro",
            "compatibility_mode": "backward",
            "schema": {"fields": [{"name": "id", "type": "long"}]},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_define_job_returns_created(client: AsyncClient) -> None:
    response = await client.post(_JOBS, json=_job_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "orders-enrichment"
    assert body["status"] == "defined"
    assert body["delivery_guarantee"] == "exactly_once"
    assert body["checkpoint_config"]["interval_ms"] == 30_000


async def test_iceberg_with_at_least_once_is_unprocessable(client: AsyncClient) -> None:
    response = await client.post(
        _JOBS, json=_job_payload(sink_kind="iceberg", guarantee="at_least_once")
    )
    assert response.status_code == 422


async def test_define_with_contract_reference(client: AsyncClient) -> None:
    contract_id = await _make_contract(client)
    response = await client.post(_JOBS, json=_job_payload(contract_id=contract_id))
    assert response.status_code == 201
    assert response.json()["contract_id"] == contract_id


async def test_define_with_unknown_contract_is_unprocessable(client: AsyncClient) -> None:
    response = await client.post(
        _JOBS,
        json=_job_payload(contract_id="9b3c9215-e635-4d07-a379-ca21864ebddb"),
    )
    assert response.status_code == 422


async def test_submit_moves_job_to_running(client: AsyncClient) -> None:
    job = (await client.post(_JOBS, json=_job_payload())).json()
    response = await client.post(f"{_JOBS}/{job['id']}/submit")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["runtime_ref"] is not None


async def test_suspend_records_savepoint_then_resume(client: AsyncClient) -> None:
    job = (await client.post(_JOBS, json=_job_payload())).json()
    await client.post(f"{_JOBS}/{job['id']}/submit")
    suspended = (await client.post(f"{_JOBS}/{job['id']}/suspend")).json()
    assert suspended["status"] == "suspended"
    assert suspended["savepoint_location"] is not None
    resumed = (await client.post(f"{_JOBS}/{job['id']}/resume")).json()
    assert resumed["status"] == "running"


async def test_trigger_savepoint_keeps_running(client: AsyncClient) -> None:
    job = (await client.post(_JOBS, json=_job_payload())).json()
    await client.post(f"{_JOBS}/{job['id']}/submit")
    response = await client.post(f"{_JOBS}/{job['id']}/savepoints")
    body = response.json()
    assert body["status"] == "running"
    assert body["savepoint_location"] is not None


async def test_cancel_job(client: AsyncClient) -> None:
    job = (await client.post(_JOBS, json=_job_payload())).json()
    await client.post(f"{_JOBS}/{job['id']}/submit")
    response = await client.post(f"{_JOBS}/{job['id']}/cancel")
    assert response.json()["status"] == "cancelled"


async def test_change_checkpoint_config(client: AsyncClient) -> None:
    job = (await client.post(_JOBS, json=_job_payload())).json()
    response = await client.put(
        f"{_JOBS}/{job['id']}/checkpoint-config",
        json={"checkpoint": {"interval_ms": 5_000, "max_concurrent": 2}},
    )
    body = response.json()
    assert body["checkpoint_config"]["interval_ms"] == 5_000
    assert body["checkpoint_config"]["max_concurrent"] == 2


async def test_list_filters_by_status_and_sink(client: AsyncClient) -> None:
    first = (await client.post(_JOBS, json=_job_payload("job-one"))).json()
    await client.post(
        _JOBS, json=_job_payload("job-two", sink_kind="kafka_topic", guarantee="at_least_once")
    )
    await client.post(f"{_JOBS}/{first['id']}/submit")

    running = await client.get(_JOBS, params={"status": "running"})
    assert [item["name"] for item in running.json()["items"]] == ["job-one"]

    iceberg = await client.get(_JOBS, params={"sink_kind": "iceberg"})
    assert [item["name"] for item in iceberg.json()["items"]] == ["job-one"]


async def test_get_job(client: AsyncClient) -> None:
    job = (await client.post(_JOBS, json=_job_payload())).json()
    response = await client.get(f"{_JOBS}/{job['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == job["id"]


async def test_missing_token_is_unauthorized(client: AsyncClient) -> None:
    response = await client.get(_JOBS, headers={"Authorization": ""})
    assert response.status_code == 401


async def test_readonly_cannot_define(readonly_client: AsyncClient) -> None:
    response = await readonly_client.post(_JOBS, json=_job_payload())
    assert response.status_code == 403
