from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, status
from starlette.responses import JSONResponse

from cascade.application.processing.commands import (
    ChangeCheckpointConfigCommand,
    CheckpointInput,
    DefineJobCommand,
    EndpointInput,
    RestartInput,
)
from cascade.application.processing.queries import GetJobQuery, ListJobsQuery
from cascade.infrastructure.cache.base import IdempotentResponse
from cascade.infrastructure.security.jwt import Principal
from cascade.presentation.api.dependencies import (
    CacheDep,
    ProcessingServiceDep,
    SettingsDep,
)
from cascade.presentation.api.schemas.common import PageMeta, PaginatedResponse
from cascade.presentation.api.schemas.processing import (
    ChangeCheckpointRequest,
    CheckpointPayload,
    DefineJobRequest,
    JobResponse,
)
from cascade.presentation.api.security import require_scopes

router = APIRouter(prefix="/api/v1/jobs", tags=["processing"])

WriteScope = Annotated[Principal, Depends(require_scopes("processing:write"))]
ReadScope = Annotated[Principal, Depends(require_scopes("processing:read"))]


def _checkpoint_input(payload: CheckpointPayload) -> CheckpointInput:
    return CheckpointInput(
        interval_ms=payload.interval_ms,
        timeout_ms=payload.timeout_ms,
        min_pause_ms=payload.min_pause_ms,
        max_concurrent=payload.max_concurrent,
    )


@router.post(
    "",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Define a stream job",
)
async def define_job(
    payload: DefineJobRequest,
    service: ProcessingServiceDep,
    cache: CacheDep,
    settings: SettingsDep,
    principal: WriteScope,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    scoped_key = f"jobs:define:{principal.subject}:{idempotency_key}" if idempotency_key else None
    if scoped_key is not None:
        replayed = await cache.get_idempotent(scoped_key)
        if replayed is not None:
            return JSONResponse(status_code=replayed.status_code, content=json.loads(replayed.body))

    command = DefineJobCommand(
        name=payload.name,
        source=EndpointInput(kind=payload.source.kind, resource=payload.source.resource),
        sink=EndpointInput(kind=payload.sink.kind, resource=payload.sink.resource),
        delivery_guarantee=payload.delivery_guarantee,
        checkpoint=_checkpoint_input(payload.checkpoint),
        restart=RestartInput(
            kind=payload.restart.kind,
            attempts=payload.restart.attempts,
            delay_ms=payload.restart.delay_ms,
        ),
        parallelism=payload.parallelism,
        contract_id=payload.contract_id,
        description=payload.description,
    )
    view = await service.define_job(command)
    body = JobResponse.from_view(view).model_dump(mode="json")

    if scoped_key is not None:
        await cache.store_idempotent(
            scoped_key,
            IdempotentResponse(status_code=status.HTTP_201_CREATED, body=json.dumps(body)),
            settings.idempotency_ttl_seconds,
        )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body)


@router.get("", response_model=PaginatedResponse[JobResponse], summary="List stream jobs")
async def list_jobs(
    service: ProcessingServiceDep,
    _principal: ReadScope,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    sink_kind: Annotated[str | None, Query()] = None,
    delivery_guarantee: Annotated[str | None, Query()] = None,
    contract_id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[str, Query()] = "created_at",
    descending: Annotated[bool, Query()] = True,
) -> PaginatedResponse[JobResponse]:
    result = await service.list_jobs(
        ListJobsQuery(
            status=status_filter,
            sink_kind=sink_kind,
            delivery_guarantee=delivery_guarantee,
            contract_id=contract_id,
            page=page,
            size=size,
            sort_by=sort_by,
            descending=descending,
        )
    )
    return PaginatedResponse[JobResponse](
        items=[JobResponse.from_view(item) for item in result.items],
        meta=PageMeta(page=result.page, size=result.size, total=result.total, pages=result.pages),
    )


@router.get("/{job_id}", response_model=JobResponse, summary="Get a stream job")
async def get_job(
    service: ProcessingServiceDep,
    _principal: ReadScope,
    job_id: Annotated[str, Path()],
) -> JobResponse:
    view = await service.get_job(GetJobQuery(job_id=job_id))
    return JobResponse.from_view(view)


@router.post("/{job_id}/submit", response_model=JobResponse, summary="Submit a job to Flink")
async def submit_job(
    service: ProcessingServiceDep,
    _principal: WriteScope,
    job_id: Annotated[str, Path()],
) -> JobResponse:
    view = await service.submit_job(job_id)
    return JobResponse.from_view(view)


@router.post(
    "/{job_id}/suspend",
    response_model=JobResponse,
    summary="Suspend a job with a savepoint",
)
async def suspend_job(
    service: ProcessingServiceDep,
    _principal: WriteScope,
    job_id: Annotated[str, Path()],
) -> JobResponse:
    view = await service.suspend_job(job_id)
    return JobResponse.from_view(view)


@router.post(
    "/{job_id}/resume",
    response_model=JobResponse,
    summary="Resume a job from its savepoint",
)
async def resume_job(
    service: ProcessingServiceDep,
    _principal: WriteScope,
    job_id: Annotated[str, Path()],
) -> JobResponse:
    view = await service.resume_job(job_id)
    return JobResponse.from_view(view)


@router.post("/{job_id}/cancel", response_model=JobResponse, summary="Cancel a job")
async def cancel_job(
    service: ProcessingServiceDep,
    _principal: WriteScope,
    job_id: Annotated[str, Path()],
) -> JobResponse:
    view = await service.cancel_job(job_id)
    return JobResponse.from_view(view)


@router.post(
    "/{job_id}/savepoints",
    response_model=JobResponse,
    summary="Trigger a savepoint without stopping",
)
async def trigger_savepoint(
    service: ProcessingServiceDep,
    _principal: WriteScope,
    job_id: Annotated[str, Path()],
) -> JobResponse:
    view = await service.trigger_savepoint(job_id)
    return JobResponse.from_view(view)


@router.put(
    "/{job_id}/checkpoint-config",
    response_model=JobResponse,
    summary="Change the checkpoint configuration",
)
async def change_checkpoint_config(
    payload: ChangeCheckpointRequest,
    service: ProcessingServiceDep,
    _principal: WriteScope,
    job_id: Annotated[str, Path()],
) -> JobResponse:
    view = await service.change_checkpoint_config(
        ChangeCheckpointConfigCommand(
            job_id=job_id, checkpoint=_checkpoint_input(payload.checkpoint)
        )
    )
    return JobResponse.from_view(view)
