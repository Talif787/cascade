from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, status
from starlette.responses import JSONResponse

from cascade.application.serving.commands import (
    ChangeRefreshScheduleCommand,
    ColumnInput,
    FilterInput,
    MeasureInput,
    RegisterServingViewCommand,
    RunQueryCommand,
)
from cascade.application.serving.queries import (
    GetServingViewQuery,
    ListServingViewsQuery,
)
from cascade.infrastructure.cache.base import IdempotentResponse
from cascade.infrastructure.security.jwt import Principal
from cascade.presentation.api.dependencies import (
    CacheDep,
    ServingServiceDep,
    SettingsDep,
)
from cascade.presentation.api.schemas.common import PageMeta, PaginatedResponse
from cascade.presentation.api.schemas.serving import (
    CatalogEntryResponse,
    CatalogResponse,
    ChangeScheduleRequest,
    QueryResponse,
    RegisterServingViewRequest,
    RunQueryRequest,
    ServingViewResponse,
)
from cascade.presentation.api.security import require_scopes

router = APIRouter(prefix="/api/v1/serving-views", tags=["serving"])

WriteScope = Annotated[Principal, Depends(require_scopes("serving:write"))]
ReadScope = Annotated[Principal, Depends(require_scopes("serving:read"))]


@router.post(
    "",
    response_model=ServingViewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a serving view",
)
async def register_serving_view(
    payload: RegisterServingViewRequest,
    service: ServingServiceDep,
    cache: CacheDep,
    settings: SettingsDep,
    principal: WriteScope,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    scoped_key = (
        f"serving:register:{principal.subject}:{idempotency_key}" if idempotency_key else None
    )
    if scoped_key is not None:
        replayed = await cache.get_idempotent(scoped_key)
        if replayed is not None:
            return JSONResponse(status_code=replayed.status_code, content=json.loads(replayed.body))

    command = RegisterServingViewCommand(
        name=payload.name,
        source_dataset_id=payload.source_dataset_id,
        engine=payload.engine,
        columns=tuple(
            ColumnInput(name=c.name, type=c.type, role=c.role, nullable=c.nullable)
            for c in payload.columns
        ),
        order_by=tuple(payload.order_by),
        partition_by=payload.partition_by,
        refresh_mode=payload.refresh_mode,
        refresh_cron=payload.refresh_cron,
        refresh_enabled=payload.refresh_enabled,
        description=payload.description,
    )
    view = await service.register_serving_view(command)
    body = ServingViewResponse.from_view(view).model_dump(mode="json")

    if scoped_key is not None:
        await cache.store_idempotent(
            scoped_key,
            IdempotentResponse(status_code=status.HTTP_201_CREATED, body=json.dumps(body)),
            settings.idempotency_ttl_seconds,
        )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body)


@router.get("", response_model=PaginatedResponse[ServingViewResponse], summary="List serving views")
async def list_serving_views(
    service: ServingServiceDep,
    _principal: ReadScope,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    engine: Annotated[str | None, Query()] = None,
    source_dataset_id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[str, Query()] = "created_at",
    descending: Annotated[bool, Query()] = True,
) -> PaginatedResponse[ServingViewResponse]:
    result = await service.list_serving_views(
        ListServingViewsQuery(
            status=status_filter,
            engine=engine,
            source_dataset_id=source_dataset_id,
            page=page,
            size=size,
            sort_by=sort_by,
            descending=descending,
        )
    )
    return PaginatedResponse[ServingViewResponse](
        items=[ServingViewResponse.from_view(item) for item in result.items],
        meta=PageMeta(page=result.page, size=result.size, total=result.total, pages=result.pages),
    )


@router.get("/catalog", response_model=CatalogResponse, summary="List queryable views")
async def get_catalog(
    service: ServingServiceDep,
    _principal: ReadScope,
) -> CatalogResponse:
    entries = await service.get_catalog()
    return CatalogResponse(entries=[CatalogEntryResponse.from_view(entry) for entry in entries])


@router.get("/{view_id}", response_model=ServingViewResponse, summary="Get a serving view")
async def get_serving_view(
    service: ServingServiceDep,
    _principal: ReadScope,
    view_id: Annotated[str, Path()],
) -> ServingViewResponse:
    view = await service.get_serving_view(GetServingViewQuery(view_id=view_id))
    return ServingViewResponse.from_view(view)


@router.post("/{view_id}/sync", response_model=ServingViewResponse, summary="Sync a serving view")
async def sync_serving_view(
    service: ServingServiceDep,
    _principal: WriteScope,
    view_id: Annotated[str, Path()],
) -> ServingViewResponse:
    view = await service.sync_serving_view(view_id)
    return ServingViewResponse.from_view(view)


@router.post(
    "/{view_id}/reconcile",
    response_model=ServingViewResponse,
    summary="Reconcile staleness against the source dataset",
)
async def reconcile_serving_view(
    service: ServingServiceDep,
    _principal: WriteScope,
    view_id: Annotated[str, Path()],
) -> ServingViewResponse:
    view = await service.reconcile_serving_view(view_id)
    return ServingViewResponse.from_view(view)


@router.put(
    "/{view_id}/schedule",
    response_model=ServingViewResponse,
    summary="Change the refresh schedule",
)
async def change_schedule(
    payload: ChangeScheduleRequest,
    service: ServingServiceDep,
    _principal: WriteScope,
    view_id: Annotated[str, Path()],
) -> ServingViewResponse:
    view = await service.change_schedule(
        ChangeRefreshScheduleCommand(
            view_id=view_id,
            refresh_cron=payload.refresh_cron,
            refresh_enabled=payload.refresh_enabled,
        )
    )
    return ServingViewResponse.from_view(view)


@router.post(
    "/{view_id}/retire", response_model=ServingViewResponse, summary="Retire a serving view"
)
async def retire_serving_view(
    service: ServingServiceDep,
    _principal: WriteScope,
    view_id: Annotated[str, Path()],
) -> ServingViewResponse:
    view = await service.retire_serving_view(view_id)
    return ServingViewResponse.from_view(view)


@router.post(
    "/{view_id}/query",
    response_model=QueryResponse,
    summary="Run an analytics query against a serving view",
)
async def run_query(
    payload: RunQueryRequest,
    service: ServingServiceDep,
    _principal: ReadScope,
    view_id: Annotated[str, Path()],
) -> QueryResponse:
    result = await service.run_query(
        RunQueryCommand(
            view_id=view_id,
            dimensions=tuple(payload.dimensions),
            measures=tuple(
                MeasureInput(column=m.column, aggregation=m.aggregation) for m in payload.measures
            ),
            filters=tuple(
                FilterInput(column=f.column, op=f.op, values=tuple(f.values))
                for f in payload.filters
            ),
            limit=payload.limit,
        )
    )
    return QueryResponse.from_view(result)
