from __future__ import annotations

from typing import Any

from cascade.application.lakehouse.transformation import TransformationSpec
from cascade.domain.lakehouse.value_objects import QualityCheck, QualityCheckKind


def _test_for(check: QualityCheck) -> dict[str, Any]:
    if check.kind is QualityCheckKind.NOT_NULL:
        return {"test": "not_null", "column": check.column}
    if check.kind is QualityCheckKind.UNIQUE:
        return {"test": "unique", "column": check.column}
    if check.kind is QualityCheckKind.ACCEPTED_VALUES:
        return {
            "test": "accepted_values",
            "column": check.column,
            "values": list(check.accepted_values),
        }
    if check.kind is QualityCheckKind.ROW_COUNT_MIN:
        return {"test": "row_count", "min": check.threshold}
    return {"test": "freshness", "max_age_minutes": check.threshold}


def build_dbt_run_config(spec: TransformationSpec) -> dict[str, Any]:
    """Translate a transformation spec into a dbt selector and test plan."""

    return {
        "select": spec.identifier,
        "target_table": spec.name,
        "materialized": spec.materialization.value,
        "layer": spec.layer.value,
        "tests": [_test_for(check) for check in spec.quality_checks],
    }
