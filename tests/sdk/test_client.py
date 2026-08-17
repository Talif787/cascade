from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from cascade.sdk import (
    CascadeProducerClient,
    ContractResolutionError,
    RecordValidationError,
)

_CONTRACT: dict[str, Any] = {
    "id": "c-1",
    "name": "orders-value",
    "schema_versions": [
        {
            "version": 1,
            "status": "published",
            "registry_id": 5,
            "fields": [{"name": "id", "type": "long"}],
        },
        {
            "version": 2,
            "status": "published",
            "registry_id": 9,
            "fields": [
                {"name": "id", "type": "long"},
                {"name": "amount", "type": "double", "has_default": True},
            ],
        },
    ],
}


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/v1/contracts/c-1":
        return httpx.Response(200, json=_CONTRACT)
    if request.url.path == "/api/v1/contracts/missing":
        return httpx.Response(404, json={"detail": "not found"})
    if request.url.path == "/api/v1/contracts":
        return httpx.Response(200, json={"items": [_CONTRACT]})
    return httpx.Response(500, json={"detail": "unexpected"})


def _client() -> CascadeProducerClient:
    return CascadeProducerClient(
        "http://control-plane", token="t", transport=httpx.MockTransport(_handler)
    )


async def test_resolve_by_id_picks_latest_published() -> None:
    schema = await _client().resolve_by_id("c-1")
    assert schema.version == 2
    assert schema.registry_id == 9
    assert {f.name for f in schema.fields} == {"id", "amount"}


async def test_resolve_by_id_missing_raises() -> None:
    with pytest.raises(ContractResolutionError):
        await _client().resolve_by_id("missing")


async def test_resolve_by_name_matches() -> None:
    schema = await _client().resolve_by_name("orders-value")
    assert schema.contract_id == "c-1"


async def test_resolve_by_name_unknown_raises() -> None:
    with pytest.raises(ContractResolutionError):
        await _client().resolve_by_name("unknown")


async def test_validate_record_rejects_bad_payload() -> None:
    with pytest.raises(RecordValidationError):
        await _client().validate_record("c-1", {"id": "not-an-int"})


async def test_validate_record_accepts_good_payload() -> None:
    schema = await _client().validate_record("c-1", {"id": 1, "amount": 2.5})
    assert schema.registry_id == 9


def test_contract_payload_is_json_serialisable() -> None:
    # guards the fixture against accidental non-serialisable edits
    assert json.loads(json.dumps(_CONTRACT))["name"] == "orders-value"
