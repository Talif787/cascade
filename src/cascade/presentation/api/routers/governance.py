from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from cascade.application.governance.commands import (
    ChangeFreshnessTargetCommand,
    ImportCostsCommand,
    RecordCostCommand,
    RegisterSloCommand,
)
from cascade.application.governance.queries import (
    CostReportQuery,
    GetLineageQuery,
    GetSloQuery,
    ListSlosQuery,
)
from cascade.infrastructure.security.jwt import Principal
from cascade.presentation.api.dependencies import GovernanceServiceDep
from cascade.presentation.api.schemas.common import PageMeta, PaginatedResponse
from cascade.presentation.api.schemas.governance import (
    ChangeTargetRequest,
    CostEntryResponse,
    CostReportResponse,
    EvaluateAllResponse,
    ImportCostsRequest,
    ImportResultResponse,
    LineageResponse,
    RecordCostRequest,
    RegisterSloRequest,
    SloResponse,
)
from cascade.presentation.api.security import require_scopes

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

WriteScope = Annotated[Principal, Depends(require_scopes("governance:write"))]
ReadScope = Annotated[Principal, Depends(require_scopes("governance:read"))]


@router.post(
    "/slos",
    response_model=SloResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a freshness SLO",
)
async def register_slo(
    payload: RegisterSloRequest,
    service: GovernanceServiceDep,
    _principal: WriteScope,
) -> SloResponse:
    view = await service.register_slo(
        RegisterSloCommand(
            name=payload.name,
            asset_kind=payload.asset_kind,
            asset_id=payload.asset_id,
            max_staleness_minutes=payload.max_staleness_minutes,
            severity=payload.severity,
            owner=payload.owner,
            description=payload.description,
        )
    )
    return SloResponse.from_view(view)


@router.get("/slos", response_model=PaginatedResponse[SloResponse], summary="List SLOs")
async def list_slos(
    service: GovernanceServiceDep,
    _principal: ReadScope,
    asset_kind: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    state: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[str, Query()] = "created_at",
    descending: Annotated[bool, Query()] = True,
) -> PaginatedResponse[SloResponse]:
    result = await service.list_slos(
        ListSlosQuery(
            asset_kind=asset_kind,
            status=status_filter,
            state=state,
            page=page,
            size=size,
            sort_by=sort_by,
            descending=descending,
        )
    )
    return PaginatedResponse[SloResponse](
        items=[SloResponse.from_view(item) for item in result.items],
        meta=PageMeta(page=result.page, size=result.size, total=result.total, pages=result.pages),
    )


@router.post(
    "/slos/evaluate", response_model=EvaluateAllResponse, summary="Evaluate all active SLOs"
)
async def evaluate_all(
    service: GovernanceServiceDep,
    _principal: WriteScope,
) -> EvaluateAllResponse:
    views = await service.evaluate_all()
    return EvaluateAllResponse(evaluated=[SloResponse.from_view(v) for v in views])


@router.get("/slos/{slo_id}", response_model=SloResponse, summary="Get an SLO")
async def get_slo(
    service: GovernanceServiceDep,
    _principal: ReadScope,
    slo_id: Annotated[str, Path()],
) -> SloResponse:
    view = await service.get_slo(GetSloQuery(slo_id=slo_id))
    return SloResponse.from_view(view)


@router.post("/slos/{slo_id}/evaluate", response_model=SloResponse, summary="Evaluate one SLO")
async def evaluate_slo(
    service: GovernanceServiceDep,
    _principal: WriteScope,
    slo_id: Annotated[str, Path()],
) -> SloResponse:
    view = await service.evaluate_slo(slo_id)
    return SloResponse.from_view(view)


@router.put(
    "/slos/{slo_id}/target", response_model=SloResponse, summary="Change the freshness target"
)
async def change_target(
    payload: ChangeTargetRequest,
    service: GovernanceServiceDep,
    _principal: WriteScope,
    slo_id: Annotated[str, Path()],
) -> SloResponse:
    view = await service.change_target(
        ChangeFreshnessTargetCommand(
            slo_id=slo_id, max_staleness_minutes=payload.max_staleness_minutes
        )
    )
    return SloResponse.from_view(view)


@router.post("/slos/{slo_id}/suspend", response_model=SloResponse, summary="Suspend an SLO")
async def suspend_slo(
    service: GovernanceServiceDep,
    _principal: WriteScope,
    slo_id: Annotated[str, Path()],
) -> SloResponse:
    view = await service.suspend_slo(slo_id)
    return SloResponse.from_view(view)


@router.post("/slos/{slo_id}/resume", response_model=SloResponse, summary="Resume an SLO")
async def resume_slo(
    service: GovernanceServiceDep,
    _principal: WriteScope,
    slo_id: Annotated[str, Path()],
) -> SloResponse:
    view = await service.resume_slo(slo_id)
    return SloResponse.from_view(view)


@router.post("/slos/{slo_id}/retire", response_model=SloResponse, summary="Retire an SLO")
async def retire_slo(
    service: GovernanceServiceDep,
    _principal: WriteScope,
    slo_id: Annotated[str, Path()],
) -> SloResponse:
    view = await service.retire_slo(slo_id)
    return SloResponse.from_view(view)


@router.post(
    "/costs",
    response_model=CostEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a cost entry",
)
async def record_cost(
    payload: RecordCostRequest,
    service: GovernanceServiceDep,
    _principal: WriteScope,
) -> CostEntryResponse:
    view = await service.record_cost(
        RecordCostCommand(
            asset_kind=payload.asset_kind,
            asset_id=payload.asset_id,
            category=payload.category,
            amount_cents=payload.amount_cents,
            currency=payload.currency,
            period_start=payload.period_start,
            period_end=payload.period_end,
            source=payload.source,
        )
    )
    return CostEntryResponse.from_view(view)


@router.post(
    "/costs/import", response_model=ImportResultResponse, summary="Import costs from the source"
)
async def import_costs(
    payload: ImportCostsRequest,
    service: GovernanceServiceDep,
    _principal: WriteScope,
) -> ImportResultResponse:
    view = await service.import_costs(
        ImportCostsCommand(window_start=payload.window_start, window_end=payload.window_end)
    )
    return ImportResultResponse.from_view(view)


@router.get("/costs/report", response_model=CostReportResponse, summary="Cost report")
async def cost_report(
    service: GovernanceServiceDep,
    _principal: ReadScope,
    window_start: Annotated[str | None, Query()] = None,
    window_end: Annotated[str | None, Query()] = None,
) -> CostReportResponse:
    from datetime import datetime

    view = await service.cost_report(
        CostReportQuery(
            window_start=datetime.fromisoformat(window_start) if window_start else None,
            window_end=datetime.fromisoformat(window_end) if window_end else None,
        )
    )
    return CostReportResponse.from_view(view)


@router.get(
    "/lineage/{asset_kind}/{asset_id}",
    response_model=LineageResponse,
    summary="Get the lineage graph rooted at an asset",
)
async def get_lineage(
    service: GovernanceServiceDep,
    _principal: ReadScope,
    asset_kind: Annotated[str, Path()],
    asset_id: Annotated[str, Path()],
) -> LineageResponse:
    view = await service.get_lineage(GetLineageQuery(asset_kind=asset_kind, asset_id=asset_id))
    return LineageResponse.from_view(view)
