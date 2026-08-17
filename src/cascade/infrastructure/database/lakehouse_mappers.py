from __future__ import annotations

from typing import Any

from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.lakehouse.aggregate import Dataset
from cascade.domain.lakehouse.value_objects import (
    DatasetId,
    DatasetName,
    DatasetRef,
    DatasetStatus,
    Materialization,
    MedallionLayer,
    QualityCheck,
    QualityCheckKind,
    QualityOutcome,
    QualityStatus,
    Schedule,
    Transformation,
    TransformationEngine,
)
from cascade.infrastructure.database.models import DatasetModel


def _transformation_to_dict(t: Transformation) -> dict[str, Any]:
    return {
        "engine": t.engine.value,
        "identifier": t.identifier,
        "materialization": t.materialization.value,
    }


def _schedule_to_dict(s: Schedule) -> dict[str, Any]:
    return {"cron": s.cron, "timezone": s.timezone, "enabled": s.enabled}


def _ref_to_dict(ref: DatasetRef) -> dict[str, Any]:
    return {"id": str(ref.dataset_id), "name": str(ref.name), "layer": ref.layer.value}


def _check_to_dict(check: QualityCheck) -> dict[str, Any]:
    return {
        "kind": check.kind.value,
        "column": check.column,
        "threshold": check.threshold,
        "accepted_values": list(check.accepted_values),
    }


def _outcome_to_dict(outcome: QualityOutcome) -> dict[str, Any]:
    return {"name": outcome.name, "passed": outcome.passed, "detail": outcome.detail}


def _ref_from_dict(payload: dict[str, Any]) -> DatasetRef:
    return DatasetRef(
        dataset_id=DatasetId.from_string(payload["id"]),
        name=DatasetName(payload["name"]),
        layer=MedallionLayer(payload["layer"]),
    )


def _check_from_dict(payload: dict[str, Any]) -> QualityCheck:
    return QualityCheck(
        kind=QualityCheckKind(payload["kind"]),
        column=payload.get("column"),
        threshold=payload.get("threshold"),
        accepted_values=tuple(payload.get("accepted_values", [])),
    )


def _outcome_from_dict(payload: dict[str, Any]) -> QualityOutcome:
    return QualityOutcome(
        name=payload["name"], passed=payload["passed"], detail=payload.get("detail", "")
    )


def dataset_to_model(dataset: Dataset) -> DatasetModel:
    return DatasetModel(
        id=dataset.id.value,
        name=str(dataset.name),
        layer=dataset.layer.value,
        transformation=_transformation_to_dict(dataset.transformation),
        upstreams=[_ref_to_dict(ref) for ref in dataset.upstreams],
        schedule=_schedule_to_dict(dataset.schedule),
        quality_checks=[_check_to_dict(c) for c in dataset.quality_checks],
        contract_id=dataset.contract_id.value if dataset.contract_id is not None else None,
        status=dataset.status.value,
        quality_status=dataset.quality_status.value,
        last_run_ref=dataset.last_run_ref,
        last_row_count=dataset.last_row_count,
        last_materialized_at=dataset.last_materialized_at,
        last_quality_outcomes=[_outcome_to_dict(o) for o in dataset.last_quality_outcomes],
        description=dataset.description,
        version=dataset.version,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


def model_to_dataset(model: DatasetModel) -> Dataset:
    return Dataset(
        DatasetId(model.id),
        name=DatasetName(model.name),
        layer=MedallionLayer(model.layer),
        transformation=Transformation(
            engine=TransformationEngine(model.transformation["engine"]),
            identifier=model.transformation["identifier"],
            materialization=Materialization(model.transformation["materialization"]),
        ),
        upstreams=tuple(_ref_from_dict(ref) for ref in model.upstreams),
        schedule=Schedule(
            cron=model.schedule["cron"],
            timezone=model.schedule["timezone"],
            enabled=model.schedule["enabled"],
        ),
        quality_checks=tuple(_check_from_dict(c) for c in model.quality_checks),
        contract_id=DataContractId(model.contract_id) if model.contract_id is not None else None,
        status=DatasetStatus(model.status),
        quality_status=QualityStatus(model.quality_status),
        last_run_ref=model.last_run_ref,
        last_row_count=model.last_row_count,
        last_materialized_at=model.last_materialized_at,
        last_quality_outcomes=tuple(_outcome_from_dict(o) for o in model.last_quality_outcomes),
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )
