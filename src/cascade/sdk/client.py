from __future__ import annotations

from typing import Any

import httpx

from cascade.sdk.validator import ResolvedSchema, SchemaFieldSpec


class ContractResolutionError(RuntimeError):
    """Raised when a contract or version cannot be resolved."""


class CascadeProducerClient:
    """A thin client a producer uses to fetch and enforce data contracts.

    Depends only on httpx and the standard library so it can be vendored into a
    data-plane producer without pulling in the control-plane server.
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._transport = transport
        self._timeout = timeout_seconds

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            transport=self._transport,
            timeout=self._timeout,
        )

    async def resolve_by_id(self, contract_id: str) -> ResolvedSchema:
        async with self._client() as client:
            response = await client.get(f"/api/v1/contracts/{contract_id}")
        if response.status_code == 404:
            raise ContractResolutionError(f"contract {contract_id} was not found")
        if response.status_code >= 400:
            raise ContractResolutionError(
                f"could not resolve contract {contract_id}: {response.status_code}"
            )
        return _to_schema(response.json())

    async def resolve_by_name(self, name: str) -> ResolvedSchema:
        async with self._client() as client:
            response = await client.get("/api/v1/contracts", params={"size": 100})
        if response.status_code >= 400:
            raise ContractResolutionError(f"could not list contracts: {response.status_code}")
        for item in response.json().get("items", []):
            if item.get("name") == name:
                return _to_schema(item)
        raise ContractResolutionError(f"no contract named {name!r}")

    async def validate_record(self, contract_id: str, record: dict[str, Any]) -> ResolvedSchema:
        schema = await self.resolve_by_id(contract_id)
        schema.validate_record(record)
        return schema


def _latest_published(payload: dict[str, Any]) -> dict[str, Any]:
    versions = payload.get("schema_versions", [])
    published = [v for v in versions if v.get("status") == "published"]
    pool = published or versions
    if not pool:
        raise ContractResolutionError("contract has no schema versions")
    return max(pool, key=lambda v: v["version"])


def _to_schema(payload: dict[str, Any]) -> ResolvedSchema:
    version = _latest_published(payload)
    fields = tuple(
        SchemaFieldSpec(
            name=field["name"],
            type=field["type"],
            nullable=field.get("nullable", False),
            has_default=field.get("has_default", False),
        )
        for field in version["fields"]
    )
    return ResolvedSchema(
        contract_id=payload["id"],
        contract_name=payload["name"],
        version=version["version"],
        registry_id=version.get("registry_id"),
        fields=fields,
    )
