from __future__ import annotations

import uuid

from cascade.application.lakehouse.orchestration import (
    Orchestrator,
    ScheduleState,
)


class InMemoryOrchestrator(Orchestrator):
    """Tracks schedules in process without a real Airflow deployment."""

    def __init__(self) -> None:
        self._schedules: dict[str, bool] = {}

    async def upsert_schedule(self, dag_id: str, cron: str, timezone: str, enabled: bool) -> None:
        self._schedules[dag_id] = enabled

    async def trigger(self, dag_id: str) -> str:
        return f"manual__{uuid.uuid4().hex[:12]}"

    async def pause(self, dag_id: str) -> None:
        if dag_id in self._schedules:
            self._schedules[dag_id] = False

    async def status(self, dag_id: str) -> ScheduleState | None:
        if dag_id not in self._schedules:
            return None
        return ScheduleState(dag_id=dag_id, enabled=self._schedules[dag_id])
