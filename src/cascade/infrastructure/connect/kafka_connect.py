from __future__ import annotations

import httpx

from cascade.application.ingestion.runtime import (
    ConnectorHandle,
    ConnectorRuntime,
    ConnectorRuntimeError,
    ConnectorSpec,
)
from cascade.infrastructure.connect.config_builder import build_connector_config


class KafkaConnectRuntime(ConnectorRuntime):
    """Adapter for the Kafka Connect REST API (which also hosts Debezium)."""

    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def deploy(self, spec: ConnectorSpec) -> ConnectorHandle:
        config = build_connector_config(spec)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.put(
                f"{self._base_url}/connectors/{spec.name}/config", json=config
            )
        if response.status_code >= 400:
            raise ConnectorRuntimeError(
                f"deploy failed for {spec.name!r}: {response.status_code} {response.text}"
            )
        return ConnectorHandle(name=spec.name, state="RUNNING")

    async def pause(self, name: str) -> None:
        await self._empty_put(f"/connectors/{name}/pause", name, "pause")

    async def resume(self, name: str) -> None:
        await self._empty_put(f"/connectors/{name}/resume", name, "resume")

    async def delete(self, name: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.delete(f"{self._base_url}/connectors/{name}")
        if response.status_code >= 400 and response.status_code != 404:
            raise ConnectorRuntimeError(
                f"delete failed for {name!r}: {response.status_code} {response.text}"
            )

    async def status(self, name: str) -> ConnectorHandle | None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}/connectors/{name}/status")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ConnectorRuntimeError(
                f"status failed for {name!r}: {response.status_code} {response.text}"
            )
        state = response.json().get("connector", {}).get("state", "UNKNOWN")
        return ConnectorHandle(name=name, state=state)

    async def _empty_put(self, path: str, name: str, action: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.put(f"{self._base_url}{path}")
        if response.status_code >= 400:
            raise ConnectorRuntimeError(
                f"{action} failed for {name!r}: {response.status_code} {response.text}"
            )
