from __future__ import annotations

import uuid

from cascade.application.processing.runtime import (
    FlinkRuntime,
    JobHandle,
    JobSpec,
)


class InMemoryFlinkRuntime(FlinkRuntime):
    """Tracks stream-job state in process without a real Flink cluster."""

    def __init__(self) -> None:
        self._jobs: dict[str, str] = {}

    async def submit(self, spec: JobSpec) -> JobHandle:
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = "RUNNING"
        return JobHandle(job_id=job_id, state="RUNNING")

    async def stop_with_savepoint(self, job_id: str) -> str:
        self._jobs[job_id] = "FINISHED"
        return f"s3://cascade-savepoints/{job_id}/savepoint-{uuid.uuid4().hex[:8]}"

    async def trigger_savepoint(self, job_id: str) -> str:
        return f"s3://cascade-savepoints/{job_id}/savepoint-{uuid.uuid4().hex[:8]}"

    async def cancel(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    async def status(self, job_id: str) -> JobHandle | None:
        state = self._jobs.get(job_id)
        return JobHandle(job_id=job_id, state=state) if state is not None else None
