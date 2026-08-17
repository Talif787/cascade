from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from cascade.domain.ingestion.value_objects import (
    ConnectorConfig,
    ConnectorKind,
    DeadLetterPolicy,
)


class ConnectorRuntimeError(RuntimeError):
    """Raised when the external connector runtime cannot satisfy a request."""


@dataclass(frozen=True, slots=True)
class ConnectorSpec:
    name: str
    kind: ConnectorKind
    config: ConnectorConfig
    dead_letter_policy: DeadLetterPolicy


@dataclass(frozen=True, slots=True)
class ConnectorHandle:
    name: str
    state: str


class ConnectorRuntime(ABC):
    """Port for the system that actually runs source connectors."""

    @abstractmethod
    async def deploy(self, spec: ConnectorSpec) -> ConnectorHandle: ...

    @abstractmethod
    async def pause(self, name: str) -> None: ...

    @abstractmethod
    async def resume(self, name: str) -> None: ...

    @abstractmethod
    async def delete(self, name: str) -> None: ...

    @abstractmethod
    async def status(self, name: str) -> ConnectorHandle | None: ...
