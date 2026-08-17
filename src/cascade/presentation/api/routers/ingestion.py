from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, status
from starlette.responses import JSONResponse

from cascade.application.ingestion.commands import (
    ChangeDeadLetterPolicyCommand,
    DeadLetterInput,
    RecordDeadLettersCommand,
    RegisterSourceCommand,
)
from cascade.application.ingestion.queries import GetSourceQuery, ListSourcesQuery
from cascade.infrastructure.cache.base import IdempotentResponse
from cascade.infrastructure.security.jwt import Principal
from cascade.presentation.api.dependencies import (
    CacheDep,
    IngestionServiceDep,
    SettingsDep,
)
from cascade.presentation.api.schemas.common import PageMeta, PaginatedResponse
from cascade.presentation.api.schemas.ingestion import (
    ChangeDeadLetterPolicyRequest,
    DeadLetterPolicyPayload,
    RecordDeadLettersRequest,
    RegisterSourceRequest,
    SourceResponse,
)
from cascade.presentation.api.security import require_scopes

router = APIRouter(prefix="/api/v1/sources", tags=["ingestion"])

WriteScope = Annotated[Principal, Depends(require_scopes("ingestion:write"))]
ReadScope = Annotated[Principal, Depends(require_scopes("ingestion:read"))]


def _to_dead_letter_input(payload: DeadLetterPolicyPayload) -> DeadLetterInput:
    return DeadLetterInput(
        on_failure=payload.on_failure,
        dlq_topic=payload.dlq_topic,
        max_retries=payload.max_retries,
        tolerance=payload.tolerance,
    )


@router.post(
    "",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an ingestion source",
)
async def register_source(
    payload: RegisterSourceRequest,
    service: IngestionServiceDep,
    cache: CacheDep,
    settings: SettingsDep,
    principal: WriteScope,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    scoped_key = (
        f"sources:register:{principal.subject}:{idempotency_key}" if idempotency_key else None
    )
    if scoped_key is not None:
        replayed = await cache.get_idempotent(scoped_key)
        if replayed is not None:
            return JSONResponse(status_code=replayed.status_code, content=json.loads(replayed.body))

    command = RegisterSourceCommand(
        name=payload.name,
        connector_kind=payload.connector_kind,
        config=payload.config,
        contract_id=payload.contract_id,
        pipeline_id=payload.pipeline_id,
        dead_letter=_to_dead_letter_input(payload.dead_letter),
        description=payload.description,
    )
    view = await service.register_source(command)
    body = SourceResponse.from_view(view).model_dump(mode="json")

    if scoped_key is not None:
        await cache.store_idempotent(
            scoped_key,
            IdempotentResponse(status_code=status.HTTP_201_CREATED, body=json.dumps(body)),
            settings.idempotency_ttl_seconds,
        )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body)


@router.get("", response_model=PaginatedResponse[SourceResponse], summary="List sources")
async def list_sources(
    service: IngestionServiceDep,
    _principal: ReadScope,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    connector_kind: Annotated[str | None, Query()] = None,
    contract_id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[str, Query()] = "created_at",
    descending: Annotated[bool, Query()] = True,
) -> PaginatedResponse[SourceResponse]:
    result = await service.list_sources(
        ListSourcesQuery(
            status=status_filter,
            connector_kind=connector_kind,
            contract_id=contract_id,
            page=page,
            size=size,
            sort_by=sort_by,
            descending=descending,
        )
    )
    return PaginatedResponse[SourceResponse](
        items=[SourceResponse.from_view(item) for item in result.items],
        meta=PageMeta(page=result.page, size=result.size, total=result.total, pages=result.pages),
    )


@router.get("/{source_id}", response_model=SourceResponse, summary="Get a source")
async def get_source(
    service: IngestionServiceDep,
    _principal: ReadScope,
    source_id: Annotated[str, Path()],
) -> SourceResponse:
    view = await service.get_source(GetSourceQuery(source_id=source_id))
    return SourceResponse.from_view(view)


@router.post("/{source_id}/provision", response_model=SourceResponse, summary="Provision a source")
async def provision_source(
    service: IngestionServiceDep,
    _principal: WriteScope,
    source_id: Annotated[str, Path()],
) -> SourceResponse:
    view = await service.provision_source(source_id)
    return SourceResponse.from_view(view)


@router.post("/{source_id}/pause", response_model=SourceResponse, summary="Pause a source")
async def pause_source(
    service: IngestionServiceDep,
    _principal: WriteScope,
    source_id: Annotated[str, Path()],
) -> SourceResponse:
    view = await service.pause_source(source_id)
    return SourceResponse.from_view(view)


@router.post("/{source_id}/resume", response_model=SourceResponse, summary="Resume a source")
async def resume_source(
    service: IngestionServiceDep,
    _principal: WriteScope,
    source_id: Annotated[str, Path()],
) -> SourceResponse:
    view = await service.resume_source(source_id)
    return SourceResponse.from_view(view)


@router.post(
    "/{source_id}/decommission",
    response_model=SourceResponse,
    summary="Decommission a source",
)
async def decommission_source(
    service: IngestionServiceDep,
    _principal: WriteScope,
    source_id: Annotated[str, Path()],
) -> SourceResponse:
    view = await service.decommission_source(source_id)
    return SourceResponse.from_view(view)


@router.post(
    "/{source_id}/dead-letters",
    response_model=SourceResponse,
    summary="Report dead-letter records for a source",
)
async def record_dead_letters(
    payload: RecordDeadLettersRequest,
    service: IngestionServiceDep,
    _principal: WriteScope,
    source_id: Annotated[str, Path()],
) -> SourceResponse:
    view = await service.record_dead_letters(
        RecordDeadLettersCommand(source_id=source_id, count=payload.count)
    )
    return SourceResponse.from_view(view)


@router.put(
    "/{source_id}/dead-letter-policy",
    response_model=SourceResponse,
    summary="Change the dead-letter policy",
)
async def change_dead_letter_policy(
    payload: ChangeDeadLetterPolicyRequest,
    service: IngestionServiceDep,
    _principal: WriteScope,
    source_id: Annotated[str, Path()],
) -> SourceResponse:
    view = await service.change_dead_letter_policy(
        ChangeDeadLetterPolicyCommand(
            source_id=source_id, dead_letter=_to_dead_letter_input(payload.dead_letter)
        )
    )
    return SourceResponse.from_view(view)
