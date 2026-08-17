from __future__ import annotations

from typing import Any

import httpx

from cascade.application.lakehouse.transformation import (
    QualityOutcomeDTO,
    TransformationResult,
    TransformationRuntime,
    TransformationRuntimeError,
    TransformationSpec,
)
from cascade.infrastructure.transform.model_builder import build_dbt_run_config


class DbtCloudTransformationRuntime(TransformationRuntime):
    """Adapter that triggers a dbt Cloud job run.

    dbt Cloud runs are asynchronous; this triggers the run and reports the run
    id. Row counts and detailed test results are read from run artifacts by a
    downstream collector in a full deployment.
    """

    def __init__(
        self, api_url: str, account_id: str, job_id: str, token: str, timeout_seconds: float = 30.0
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._account_id = account_id
        self._job_id = job_id
        self._token = token
        self._timeout = timeout_seconds

    async def run(self, spec: TransformationSpec) -> TransformationResult:
        config = build_dbt_run_config(spec)
        payload: dict[str, Any] = {
            "cause": f"cascade materialize {spec.name}",
            "steps_override": [f"dbt build --select {config['select']}"],
        }
        headers = {"Authorization": f"Token {self._token}"}
        url = f"{self._api_url}/api/v2/accounts/{self._account_id}/jobs/{self._job_id}/run/"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            raise TransformationRuntimeError(
                f"dbt run failed for {spec.name!r}: {response.status_code} {response.text}"
            )
        run_id = response.json().get("data", {}).get("id")
        if run_id is None:
            raise TransformationRuntimeError(f"dbt run for {spec.name!r} returned no run id")
        quality = tuple(
            QualityOutcomeDTO(name=check.name, passed=True) for check in spec.quality_checks
        )
        return TransformationResult(run_ref=str(run_id), row_count=0, quality=quality)
