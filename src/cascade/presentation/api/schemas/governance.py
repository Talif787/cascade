from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cascade.application.governance.dto import (
    CostEntryView,
    CostReportView,
    ImportResultView,
    LineageView,
    SloView,
)


class RegisterSloRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=64, examples=["orders-daily-freshness"])
    asset_kind: str = Field(examples=["dataset"])
    asset_id: str = Field(examples=["9b3c9215-e635-4d07-a379-ca21864ebddb"])
    max_staleness_minutes: int = Field(gt=0, examples=[1440])
    severity: str = Field(default="medium", examples=["high"])
    owner: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=1024)


class ChangeTargetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_staleness_minutes: int = Field(gt=0, examples=[720])


class SloResponse(BaseModel):
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
    def from_view(cls, view: SloView) -> SloResponse:
        return cls(
            id=view.id,
            name=view.name,
            asset_kind=view.asset_kind,
            asset_id=view.asset_id,
            max_staleness_minutes=view.max_staleness_minutes,
            severity=view.severity,
            owner=view.owner,
            description=view.description,
            status=view.status,
            state=view.state,
            last_evaluated_at=view.last_evaluated_at,
            last_staleness_minutes=view.last_staleness_minutes,
            breach_count=view.breach_count,
            version=view.version,
            created_at=view.created_at,
            updated_at=view.updated_at,
        )


class EvaluateAllResponse(BaseModel):
    evaluated: list[SloResponse]


class RecordCostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_kind: str = Field(examples=["dataset"])
    asset_id: str
    category: str = Field(examples=["compute"])
    amount_cents: int = Field(ge=0, examples=[1234])
    currency: str = Field(default="USD", min_length=3, max_length=3)
    period_start: datetime
    period_end: datetime
    source: str = Field(default="manual", max_length=32)


class ImportCostsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_start: datetime
    window_end: datetime


class CostEntryResponse(BaseModel):
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
    def from_view(cls, view: CostEntryView) -> CostEntryResponse:
        return cls(
            id=view.id,
            asset_kind=view.asset_kind,
            asset_id=view.asset_id,
            category=view.category,
            amount_cents=view.amount_cents,
            currency=view.currency,
            period_start=view.period_start,
            period_end=view.period_end,
            source=view.source,
            recorded_at=view.recorded_at,
        )


class ImportResultResponse(BaseModel):
    imported: int
    total_cents: int

    @classmethod
    def from_view(cls, view: ImportResultView) -> ImportResultResponse:
        return cls(imported=view.imported, total_cents=view.total_cents)


class CostLineResponse(BaseModel):
    key: str
    amount_cents: int


class CostReportResponse(BaseModel):
    total_cents: int
    by_category: list[CostLineResponse]
    by_asset: list[CostLineResponse]

    @classmethod
    def from_view(cls, view: CostReportView) -> CostReportResponse:
        return cls(
            total_cents=view.total_cents,
            by_category=[
                CostLineResponse(key=line.key, amount_cents=line.amount_cents)
                for line in view.by_category
            ],
            by_asset=[
                CostLineResponse(key=line.key, amount_cents=line.amount_cents)
                for line in view.by_asset
            ],
        )


class LineageNodeResponse(BaseModel):
    kind: str
    id: str
    name: str
    status: str


class LineageEdgeResponse(BaseModel):
    from_ref: str
    to_ref: str


class LineageResponse(BaseModel):
    root: str
    nodes: list[LineageNodeResponse]
    edges: list[LineageEdgeResponse]

    @classmethod
    def from_view(cls, view: LineageView) -> LineageResponse:
        return cls(
            root=view.root,
            nodes=[
                LineageNodeResponse(kind=n.kind, id=n.id, name=n.name, status=n.status)
                for n in view.nodes
            ],
            edges=[LineageEdgeResponse(from_ref=e.from_ref, to_ref=e.to_ref) for e in view.edges],
        )
