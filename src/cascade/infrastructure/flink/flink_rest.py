from __future__ import annotations

from typing import Any

import httpx

from cascade.application.processing.runtime import (
    FlinkRuntime,
    FlinkRuntimeError,
    JobHandle,
    JobSpec,
)
from cascade.infrastructure.flink.job_builder import build_job_config


class FlinkRestRuntime(FlinkRuntime):
    """Adapter for the Flink cluster REST API.

    Job submission on a session cluster runs a registered jar with the job
    configuration; lifecycle actions (savepoints, stop, cancel) map to the
    documented REST endpoints.
    """

    def __init__(
        self,
        base_url: str,
        jar_id: str,
        entry_class: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._jar_id = jar_id
        self._entry_class = entry_class
        self._timeout = timeout_seconds

    async def submit(self, spec: JobSpec) -> JobHandle:
        config = build_job_config(spec)
        payload: dict[str, Any] = {
            "programArgs": _program_args(config),
            "parallelism": spec.parallelism,
        }
        if self._entry_class is not None:
            payload["entryClass"] = self._entry_class
        if spec.savepoint_location is not None:
            payload["savepointPath"] = spec.savepoint_location
            payload["allowNonRestoredState"] = False
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self._base_url}/jars/{self._jar_id}/run", json=payload)
        if response.status_code >= 400:
            raise FlinkRuntimeError(
                f"submit failed for {spec.name!r}: {response.status_code} {response.text}"
            )
        job_id = response.json().get("jobid")
        if not job_id:
            raise FlinkRuntimeError(f"submit for {spec.name!r} returned no job id")
        return JobHandle(job_id=job_id, state="RUNNING")

    async def stop_with_savepoint(self, job_id: str) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/jobs/{job_id}/stop", json={"drain": False}
            )
        return await self._await_savepoint(job_id, response, action="stop")

    async def trigger_savepoint(self, job_id: str) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/jobs/{job_id}/savepoints", json={"cancel-job": False}
            )
        return await self._await_savepoint(job_id, response, action="savepoint")

    async def cancel(self, job_id: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.patch(
                f"{self._base_url}/jobs/{job_id}", params={"mode": "cancel"}
            )
        if response.status_code >= 400 and response.status_code != 404:
            raise FlinkRuntimeError(
                f"cancel failed for {job_id!r}: {response.status_code} {response.text}"
            )

    async def status(self, job_id: str) -> JobHandle | None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}/jobs/{job_id}")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise FlinkRuntimeError(
                f"status failed for {job_id!r}: {response.status_code} {response.text}"
            )
        return JobHandle(job_id=job_id, state=response.json().get("state", "UNKNOWN"))

    async def _await_savepoint(self, job_id: str, response: httpx.Response, action: str) -> str:
        if response.status_code >= 400:
            raise FlinkRuntimeError(
                f"{action} failed for {job_id!r}: {response.status_code} {response.text}"
            )
        trigger_id = response.json().get("request-id")
        if not trigger_id:
            raise FlinkRuntimeError(f"{action} for {job_id!r} returned no trigger id")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            result = await client.get(f"{self._base_url}/jobs/{job_id}/savepoints/{trigger_id}")
        if result.status_code >= 400:
            raise FlinkRuntimeError(f"{action} status failed for {job_id!r}: {result.status_code}")
        operation = result.json().get("operation", {})
        location = operation.get("location")
        if not location:
            raise FlinkRuntimeError(f"{action} for {job_id!r} produced no savepoint path")
        return str(location)


def _program_args(config: dict[str, str]) -> str:
    return " ".join(f"--{key} {value}" for key, value in config.items())
