from __future__ import annotations

import httpx

from cascade.application.lakehouse.orchestration import (
    Orchestrator,
    OrchestratorError,
    ScheduleState,
)


class AirflowOrchestrator(Orchestrator):
    """Adapter for the Airflow stable REST API.

    Schedules are expressed as DAGs; enabling or pausing a schedule maps to the
    DAG is_paused flag, and triggering a run posts a new dag run.
    """

    def __init__(
        self, base_url: str, username: str, password: str, timeout_seconds: float = 15.0
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (username, password)
        self._timeout = timeout_seconds

    async def upsert_schedule(self, dag_id: str, cron: str, timezone: str, enabled: bool) -> None:
        await self._set_paused(dag_id, not enabled)

    async def trigger(self, dag_id: str) -> str:
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            response = await client.post(f"{self._base_url}/api/v1/dags/{dag_id}/dagRuns", json={})
        if response.status_code >= 400:
            raise OrchestratorError(
                f"trigger failed for {dag_id!r}: {response.status_code} {response.text}"
            )
        run_id = response.json().get("dag_run_id")
        if not run_id:
            raise OrchestratorError(f"trigger for {dag_id!r} returned no run id")
        return str(run_id)

    async def pause(self, dag_id: str) -> None:
        await self._set_paused(dag_id, True)

    async def status(self, dag_id: str) -> ScheduleState | None:
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            response = await client.get(f"{self._base_url}/api/v1/dags/{dag_id}")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise OrchestratorError(
                f"status failed for {dag_id!r}: {response.status_code} {response.text}"
            )
        return ScheduleState(dag_id=dag_id, enabled=not response.json().get("is_paused", True))

    async def _set_paused(self, dag_id: str, is_paused: bool) -> None:
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            response = await client.patch(
                f"{self._base_url}/api/v1/dags/{dag_id}",
                params={"update_mask": "is_paused"},
                json={"is_paused": is_paused},
            )
        if response.status_code >= 400 and response.status_code != 404:
            raise OrchestratorError(
                f"schedule update failed for {dag_id!r}: {response.status_code} {response.text}"
            )
