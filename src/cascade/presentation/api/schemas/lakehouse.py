from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cascade.application.lakehouse.dto import DatasetView, LineageView


class TransformationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str = Field(default="dbt", examples=["dbt"])
    identifier: str = Field(min_length=1, max_length=255, examples=["silver_orders_enriched"])
    materialization: str = Field(default="table", examples=["table"])


class SchedulePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cron: str = Field(default="0 * * * *", examples=["0 2 * * *"])
    timezone: str = Field(default="UTC")
    enabled: bool = True


class QualityCheckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(examples=["not_null"])
    column: str | None = None
    threshold: int | None = None
    accepted_values: list[str] = Field(default_factory=list)


class RegisterDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=127, examples=["silver.orders_enriched"])
    layer: str = Field(examples=["silver"])
    transformation: TransformationPayload
    schedule: SchedulePayload = Field(default_factory=SchedulePayload)
    upstream_ids: list[str] = Field(default_factory=list)
    quality_checks: list[QualityCheckPayload] = Field(default_factory=list)
    contract_id: str | None = None
    description: str = Field(default="", max_length=1024)


class ChangeScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: SchedulePayload


class TransformationResponse(BaseModel):
    engine: str
    identifier: str
    materialization: str


class ScheduleResponse(BaseModel):
    cron: str
    timezone: str
    enabled: bool


class QualityCheckResponse(BaseModel):
    kind: str
    column: str | None
    threshold: int | None
    accepted_values: list[str]


class QualityOutcomeResponse(BaseModel):
    name: str
    passed: bool
    detail: str


class DatasetRefResponse(BaseModel):
    id: str
    name: str
    layer: str


class DatasetResponse(BaseModel):
    id: str
    name: str
    layer: str
    transformation: TransformationResponse
    upstreams: list[DatasetRefResponse]
    schedule: ScheduleResponse
    quality_checks: list[QualityCheckResponse]
    contract_id: str | None
    status: str
    quality_status: str
    last_run_ref: str | None
    last_row_count: int | None
    last_materialized_at: datetime | None
    last_quality_outcomes: list[QualityOutcomeResponse]
    description: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_view(cls, view: DatasetView) -> DatasetResponse:
        return cls(
            id=view.id,
            name=view.name,
            layer=view.layer,
            transformation=TransformationResponse(
                engine=view.transformation.engine,
                identifier=view.transformation.identifier,
                materialization=view.transformation.materialization,
            ),
            upstreams=[
                DatasetRefResponse(id=r.id, name=r.name, layer=r.layer) for r in view.upstreams
            ],
            schedule=ScheduleResponse(
                cron=view.schedule.cron,
                timezone=view.schedule.timezone,
                enabled=view.schedule.enabled,
            ),
            quality_checks=[
                QualityCheckResponse(
                    kind=c.kind,
                    column=c.column,
                    threshold=c.threshold,
                    accepted_values=c.accepted_values,
                )
                for c in view.quality_checks
            ],
            contract_id=view.contract_id,
            status=view.status,
            quality_status=view.quality_status,
            last_run_ref=view.last_run_ref,
            last_row_count=view.last_row_count,
            last_materialized_at=view.last_materialized_at,
            last_quality_outcomes=[
                QualityOutcomeResponse(name=o.name, passed=o.passed, detail=o.detail)
                for o in view.last_quality_outcomes
            ],
            description=view.description,
            version=view.version,
            created_at=view.created_at,
            updated_at=view.updated_at,
        )


class LineageResponse(BaseModel):
    dataset: DatasetRefResponse
    upstreams: list[DatasetRefResponse]
    downstreams: list[DatasetRefResponse]

    @classmethod
    def from_view(cls, view: LineageView) -> LineageResponse:
        return cls(
            dataset=DatasetRefResponse(
                id=view.dataset.id, name=view.dataset.name, layer=view.dataset.layer
            ),
            upstreams=[
                DatasetRefResponse(id=r.id, name=r.name, layer=r.layer) for r in view.upstreams
            ],
            downstreams=[
                DatasetRefResponse(id=r.id, name=r.name, layer=r.layer) for r in view.downstreams
            ],
        )
