from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from cascade.domain.processing.value_objects import (
    CheckpointConfig,
    DeliveryGuarantee,
    JobSink,
    JobSource,
    RestartStrategy,
)


class FlinkRuntimeError(RuntimeError):
    """Raised when the Flink runtime cannot satisfy a request."""


@dataclass(frozen=True, slots=True)
class JobSpec:
    name: str
    source: JobSource
    sink: JobSink
    delivery_guarantee: DeliveryGuarantee
    checkpoint_config: CheckpointConfig
    restart_strategy: RestartStrategy
    parallelism: int
    savepoint_location: str | None = None


@dataclass(frozen=True, slots=True)
class JobHandle:
    job_id: str
    state: str


class FlinkRuntime(ABC):
    """Port for the Flink cluster that actually runs stream jobs."""

    @abstractmethod
    async def submit(self, spec: JobSpec) -> JobHandle: ...

    @abstractmethod
    async def stop_with_savepoint(self, job_id: str) -> str: ...

    @abstractmethod
    async def trigger_savepoint(self, job_id: str) -> str: ...

    @abstractmethod
    async def cancel(self, job_id: str) -> None: ...

    @abstractmethod
    async def status(self, job_id: str) -> JobHandle | None: ...
