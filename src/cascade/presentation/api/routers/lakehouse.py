from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, status
from starlette.responses import JSONResponse

from cascade.application.lakehouse.commands import (
    ChangeScheduleCommand,
    QualityCheckInput,
    RegisterDatasetCommand,
    ScheduleInput,
    TransformationInput,
)
from cascade.application.lakehouse.queries import (
    GetDatasetQuery,
    GetLineageQuery,
    ListDatasetsQuery,
)
from cascade.infrastructure.cache.base import IdempotentResponse
from cascade.infrastructure.security.jwt import Principal
from cascade.presentation.api.dependencies import (
    CacheDep,
    LakehouseServiceDep,
    SettingsDep,
)
from cascade.presentation.api.schemas.common import PageMeta, PaginatedResponse
from cascade.presentation.api.schemas.lakehouse import (
    ChangeScheduleRequest,
    DatasetResponse,
    LineageResponse,
    RegisterDatasetRequest,
    SchedulePayload,
)
from cascade.presentation.api.security import require_scopes

router = APIRouter(prefix="/api/v1/datasets", tags=["lakehouse"])

WriteScope = Annotated[Principal, Depends(require_scopes("lakehouse:write"))]
ReadScope = Annotated[Principal, Depends(require_scopes("lakehouse:read"))]


def _schedule_input(payload: SchedulePayload) -> ScheduleInput:
    return ScheduleInput(cron=payload.cron, timezone=payload.timezone, enabled=payload.enabled)


@router.post(
    "",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a dataset",
)
async def register_dataset(
    payload: RegisterDatasetRequest,
    service: LakehouseServiceDep,
    cache: CacheDep,
    settings: SettingsDep,
    principal: WriteScope,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    scoped_key = (
        f"datasets:register:{principal.subject}:{idempotency_key}" if idempotency_key else None
    )
    if scoped_key is not None:
        replayed = await cache.get_idempotent(scoped_key)
        if replayed is not None:
            return JSONResponse(status_code=replayed.status_code, content=json.loads(replayed.body))

    command = RegisterDatasetCommand(
        name=payload.name,
        layer=payload.layer,
        transformation=TransformationInput(
            engine=payload.transformation.engine,
            identifier=payload.transformation.identifier,
            materialization=payload.transformation.materialization,
        ),
        schedule=_schedule_input(payload.schedule),
        upstream_ids=tuple(payload.upstream_ids),
        quality_checks=tuple(
            QualityCheckInput(
                kind=q.kind,
                column=q.column,
                threshold=q.threshold,
                accepted_values=tuple(q.accepted_values),
            )
            for q in payload.quality_checks
        ),
        contract_id=payload.contract_id,
        description=payload.description,
    )
    view = await service.register_dataset(command)
    body = DatasetResponse.from_view(view).model_dump(mode="json")

    if scoped_key is not None:
        await cache.store_idempotent(
            scoped_key,
            IdempotentResponse(status_code=status.HTTP_201_CREATED, body=json.dumps(body)),
            settings.idempotency_ttl_seconds,
        )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body)


@router.get("", response_model=PaginatedResponse[DatasetResponse], summary="List datasets")
async def list_datasets(
    service: LakehouseServiceDep,
    _principal: ReadScope,
    layer: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    quality_status: Annotated[str | None, Query()] = None,
    contract_id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[str, Query()] = "created_at",
    descending: Annotated[bool, Query()] = True,
) -> PaginatedResponse[DatasetResponse]:
    result = await service.list_datasets(
        ListDatasetsQuery(
            layer=layer,
            status=status_filter,
            quality_status=quality_status,
            contract_id=contract_id,
            page=page,
            size=size,
            sort_by=sort_by,
            descending=descending,
        )
    )
    return PaginatedResponse[DatasetResponse](
        items=[DatasetResponse.from_view(item) for item in result.items],
        meta=PageMeta(page=result.page, size=result.size, total=result.total, pages=result.pages),
    )


@router.get("/{dataset_id}", response_model=DatasetResponse, summary="Get a dataset")
async def get_dataset(
    service: LakehouseServiceDep,
    _principal: ReadScope,
    dataset_id: Annotated[str, Path()],
) -> DatasetResponse:
    view = await service.get_dataset(GetDatasetQuery(dataset_id=dataset_id))
    return DatasetResponse.from_view(view)


@router.get("/{dataset_id}/lineage", response_model=LineageResponse, summary="Get dataset lineage")
async def get_lineage(
    service: LakehouseServiceDep,
    _principal: ReadScope,
    dataset_id: Annotated[str, Path()],
) -> LineageResponse:
    view = await service.get_lineage(GetLineageQuery(dataset_id=dataset_id))
    return LineageResponse.from_view(view)


@router.post(
    "/{dataset_id}/materialize",
    response_model=DatasetResponse,
    summary="Materialize a dataset",
)
async def materialize_dataset(
    service: LakehouseServiceDep,
    _principal: WriteScope,
    dataset_id: Annotated[str, Path()],
) -> DatasetResponse:
    view = await service.materialize_dataset(dataset_id)
    return DatasetResponse.from_view(view)


@router.put(
    "/{dataset_id}/schedule",
    response_model=DatasetResponse,
    summary="Change the dataset schedule",
)
async def change_schedule(
    payload: ChangeScheduleRequest,
    service: LakehouseServiceDep,
    _principal: WriteScope,
    dataset_id: Annotated[str, Path()],
) -> DatasetResponse:
    view = await service.change_schedule(
        ChangeScheduleCommand(dataset_id=dataset_id, schedule=_schedule_input(payload.schedule))
    )
    return DatasetResponse.from_view(view)


@router.post(
    "/{dataset_id}/deprecate",
    response_model=DatasetResponse,
    summary="Deprecate a dataset",
)
async def deprecate_dataset(
    service: LakehouseServiceDep,
    _principal: WriteScope,
    dataset_id: Annotated[str, Path()],
) -> DatasetResponse:
    view = await service.deprecate_dataset(dataset_id)
    return DatasetResponse.from_view(view)
