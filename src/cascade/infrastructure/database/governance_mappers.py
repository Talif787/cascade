from __future__ import annotations

from cascade.domain.governance.aggregate import ServiceLevelObjective
from cascade.domain.governance.aggregate_cost import CostEntry
from cascade.domain.governance.value_objects import (
    AssetKind,
    AssetRef,
    ComplianceState,
    CostCategory,
    CostEntryId,
    CostPeriod,
    FreshnessTarget,
    Money,
    Severity,
    SloId,
    SloName,
    SloStatus,
)
from cascade.infrastructure.database.models import CostEntryModel, SloModel


def slo_to_model(slo: ServiceLevelObjective) -> SloModel:
    return SloModel(
        id=slo.id.value,
        name=str(slo.name),
        asset_kind=slo.asset.kind.value,
        asset_id=slo.asset.asset_id,
        max_staleness_minutes=slo.target.max_staleness_minutes,
        severity=slo.severity.value,
        owner=slo.owner,
        description=slo.description,
        status=slo.status.value,
        state=slo.state.value,
        last_evaluated_at=slo.last_evaluated_at,
        last_staleness_minutes=slo.last_staleness_minutes,
        breach_count=slo.breach_count,
        version=slo.version,
        created_at=slo.created_at,
        updated_at=slo.updated_at,
    )


def model_to_slo(model: SloModel) -> ServiceLevelObjective:
    return ServiceLevelObjective(
        SloId(model.id),
        name=SloName(model.name),
        asset=AssetRef(kind=AssetKind(model.asset_kind), asset_id=model.asset_id),
        target=FreshnessTarget(max_staleness_minutes=model.max_staleness_minutes),
        severity=Severity(model.severity),
        owner=model.owner,
        description=model.description,
        status=SloStatus(model.status),
        state=ComplianceState(model.state),
        last_evaluated_at=model.last_evaluated_at,
        last_staleness_minutes=model.last_staleness_minutes,
        breach_count=model.breach_count,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


def cost_entry_to_model(entry: CostEntry) -> CostEntryModel:
    return CostEntryModel(
        id=entry.id.value,
        asset_kind=entry.asset.kind.value,
        asset_id=entry.asset.asset_id,
        category=entry.category.value,
        amount_cents=entry.amount.amount_cents,
        currency=entry.amount.currency,
        period_start=entry.period.start,
        period_end=entry.period.end,
        source=entry.source,
        version=entry.version,
        recorded_at=entry.recorded_at,
    )


def model_to_cost_entry(model: CostEntryModel) -> CostEntry:
    return CostEntry(
        CostEntryId(model.id),
        asset=AssetRef(kind=AssetKind(model.asset_kind), asset_id=model.asset_id),
        category=CostCategory(model.category),
        amount=Money(amount_cents=model.amount_cents, currency=model.currency),
        period=CostPeriod(start=model.period_start, end=model.period_end),
        source=model.source,
        recorded_at=model.recorded_at,
        version=model.version,
    )
