from __future__ import annotations

import uuid

from cascade.application.lakehouse.transformation import (
    QualityOutcomeDTO,
    TransformationResult,
    TransformationRuntime,
    TransformationSpec,
)


class InMemoryTransformationRuntime(TransformationRuntime):
    """Simulates a dbt run without an external engine.

    Quality checks are reported as passing by default. A test or local run can
    force a failure by adding a quality check on a column literally named
    "force_fail", which keeps the behaviour deterministic and demonstrable.
    """

    def __init__(self, row_count: int = 1000) -> None:
        self._row_count = row_count

    async def run(self, spec: TransformationSpec) -> TransformationResult:
        outcomes = tuple(
            QualityOutcomeDTO(
                name=check.name,
                passed=check.column != "force_fail",
                detail="" if check.column != "force_fail" else "forced failure",
            )
            for check in spec.quality_checks
        )
        return TransformationResult(
            run_ref=f"dbt-run-{uuid.uuid4().hex[:12]}",
            row_count=self._row_count,
            quality=outcomes,
        )
