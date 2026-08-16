from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, status
from starlette.responses import JSONResponse

from cascade.application.pipelines.commands import ConnectorInput, RegisterPipelineCommand
from cascade.application.pipelines.dto import PipelineView
from cascade.application.pipelines.queries import GetPipelineQuery, ListPipelinesQuery
from cascade.infrastructure.cache.base import IdempotentResponse
from cascade.infrastructure.security.jwt import Principal
from cascade.presentation.api.dependencies import CacheDep, PipelineServiceDep, SettingsDep
from cascade.presentation.api.schemas.common import PageMeta, PaginatedResponse
from cascade.presentation.api.schemas.pipelines import (
    ConnectorPayload,
    PipelineResponse,
    RegisterPipelineRequest,
)
from cascade.presentation.api.security import require_scopes

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])

WriteScope = Annotated[Principal, Depends(require_scopes("pipelines:write"))]
ReadScope = Annotated[Principal, Depends(require_scopes("pipelines:read"))]


@router.post(
    "",
    response_model=PipelineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a pipeline",
)
async def register_pipeline(
    payload: RegisterPipelineRequest,
    service: PipelineServiceDep,
    cache: CacheDep,
    settings: SettingsDep,
    principal: WriteScope,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    scoped_key = (
        f"pipelines:register:{principal.subject}:{idempotency_key}" if idempotency_key else None
    )
    if scoped_key is not None:
        replayed = await cache.get_idempotent(scoped_key)
        if replayed is not None:
            return JSONResponse(status_code=replayed.status_code, content=json.loads(replayed.body))

    command = RegisterPipelineCommand(
        name=payload.name,
        source=_to_connector_input(payload.source),
        sink=_to_connector_input(payload.sink),
        description=payload.description,
    )
    view = await service.register_pipeline(command)
    body = PipelineResponse.from_view(view).model_dump(mode="json")

    if scoped_key is not None:
        await cache.store_idempotent(
            scoped_key,
            IdempotentResponse(status_code=status.HTTP_201_CREATED, body=json.dumps(body)),
            settings.idempotency_ttl_seconds,
        )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body)


@router.get("/{pipeline_id}", response_model=PipelineResponse, summary="Get a pipeline")
async def get_pipeline(
    service: PipelineServiceDep,
    _principal: ReadScope,
    pipeline_id: Annotated[str, Path()],
) -> PipelineResponse:
    view = await service.get_pipeline(GetPipelineQuery(pipeline_id=pipeline_id))
    return PipelineResponse.from_view(view)


@router.get("", response_model=PaginatedResponse[PipelineResponse], summary="List pipelines")
async def list_pipelines(
    service: PipelineServiceDep,
    _principal: ReadScope,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[str, Query()] = "created_at",
    descending: Annotated[bool, Query()] = True,
) -> PaginatedResponse[PipelineResponse]:
    result = await service.list_pipelines(
        ListPipelinesQuery(
            status=status_filter,
            page=page,
            size=size,
            sort_by=sort_by,
            descending=descending,
        )
    )
    return PaginatedResponse[PipelineResponse](
        items=[PipelineResponse.from_view(item) for item in result.items],
        meta=PageMeta(page=result.page, size=result.size, total=result.total, pages=result.pages),
    )


@router.post("/{pipeline_id}/activate", response_model=PipelineResponse)
async def activate_pipeline(
    service: PipelineServiceDep,
    _principal: WriteScope,
    pipeline_id: Annotated[str, Path()],
) -> PipelineResponse:
    return _respond(await service.activate_pipeline(pipeline_id))


@router.post("/{pipeline_id}/pause", response_model=PipelineResponse)
async def pause_pipeline(
    service: PipelineServiceDep,
    _principal: WriteScope,
    pipeline_id: Annotated[str, Path()],
) -> PipelineResponse:
    return _respond(await service.pause_pipeline(pipeline_id))


@router.post("/{pipeline_id}/archive", response_model=PipelineResponse)
async def archive_pipeline(
    service: PipelineServiceDep,
    _principal: WriteScope,
    pipeline_id: Annotated[str, Path()],
) -> PipelineResponse:
    return _respond(await service.archive_pipeline(pipeline_id))


def _to_connector_input(payload: ConnectorPayload) -> ConnectorInput:
    return ConnectorInput(type=payload.type, resource=payload.resource, options=payload.options)


def _respond(view: PipelineView) -> PipelineResponse:
    return PipelineResponse.from_view(view)
