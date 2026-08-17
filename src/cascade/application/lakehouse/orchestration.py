from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class OrchestratorError(RuntimeError):
    """Raised when the orchestrator cannot satisfy a request."""


@dataclass(frozen=True, slots=True)
class ScheduleState:
    dag_id: str
    enabled: bool


class Orchestrator(ABC):
    """Port for the orchestrator (Airflow) that schedules materializations."""

    @abstractmethod
    async def upsert_schedule(
        self, dag_id: str, cron: str, timezone: str, enabled: bool
    ) -> None: ...

    @abstractmethod
    async def trigger(self, dag_id: str) -> str: ...

    @abstractmethod
    async def pause(self, dag_id: str) -> None: ...

    @abstractmethod
    async def status(self, dag_id: str) -> ScheduleState | None: ...
