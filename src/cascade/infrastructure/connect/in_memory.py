from __future__ import annotations

from cascade.application.ingestion.runtime import (
    ConnectorHandle,
    ConnectorRuntime,
    ConnectorSpec,
)


class InMemoryConnectorRuntime(ConnectorRuntime):
    """Tracks connector state in process without a real Kafka Connect cluster."""

    def __init__(self) -> None:
        self._connectors: dict[str, str] = {}

    async def deploy(self, spec: ConnectorSpec) -> ConnectorHandle:
        self._connectors[spec.name] = "RUNNING"
        return ConnectorHandle(name=spec.name, state="RUNNING")

    async def pause(self, name: str) -> None:
        if name in self._connectors:
            self._connectors[name] = "PAUSED"

    async def resume(self, name: str) -> None:
        if name in self._connectors:
            self._connectors[name] = "RUNNING"

    async def delete(self, name: str) -> None:
        self._connectors.pop(name, None)

    async def status(self, name: str) -> ConnectorHandle | None:
        state = self._connectors.get(name)
        return ConnectorHandle(name=name, state=state) if state is not None else None
