from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cascade.domain.governance.aggregate import ServiceLevelObjective
from cascade.domain.governance.aggregate_cost import CostEntry
from cascade.domain.governance.repository import CostSummary


@dataclass(frozen=True, slots=True)
class SloView:
    id: str
    name: str
    asset_kind: str
    asset_id: str
    max_staleness_minutes: int
    severity: str
    owner: str
    description: str
    status: str
    state: str
    last_evaluated_at: datetime | None
    last_staleness_minutes: int | None
    breach_count: int
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_aggregate(cls, slo: ServiceLevelObjective) -> SloView:
        return cls(
            id=str(slo.id),
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


@dataclass(frozen=True, slots=True)
class CostEntryView:
    id: str
    asset_kind: str
    asset_id: str
    category: str
    amount_cents: int
    currency: str
    period_start: datetime
    period_end: datetime
    source: str
    recorded_at: datetime

    @classmethod
    def from_aggregate(cls, entry: CostEntry) -> CostEntryView:
        return cls(
            id=str(entry.id),
            asset_kind=entry.asset.kind.value,
            asset_id=entry.asset.asset_id,
            category=entry.category.value,
            amount_cents=entry.amount.amount_cents,
            currency=entry.amount.currency,
            period_start=entry.period.start,
            period_end=entry.period.end,
            source=entry.source,
            recorded_at=entry.recorded_at,
        )


@dataclass(frozen=True, slots=True)
class CostLineView:
    key: str
    amount_cents: int


@dataclass(frozen=True, slots=True)
class CostReportView:
    total_cents: int
    by_category: list[CostLineView]
    by_asset: list[CostLineView]

    @classmethod
    def from_summary(cls, summary: CostSummary) -> CostReportView:
        return cls(
            total_cents=summary.total_cents,
            by_category=[
                CostLineView(key=line.key, amount_cents=line.amount_cents)
                for line in summary.by_category
            ],
            by_asset=[
                CostLineView(key=line.key, amount_cents=line.amount_cents)
                for line in summary.by_asset
            ],
        )


@dataclass(frozen=True, slots=True)
class ImportResultView:
    imported: int
    total_cents: int


@dataclass(frozen=True, slots=True)
class LineageNodeView:
    kind: str
    id: str
    name: str
    status: str


@dataclass(frozen=True, slots=True)
class LineageEdgeView:
    from_ref: str
    to_ref: str


@dataclass(frozen=True, slots=True)
class LineageView:
    root: str
    nodes: list[LineageNodeView]
    edges: list[LineageEdgeView]
