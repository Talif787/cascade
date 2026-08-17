from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, status
from starlette.responses import JSONResponse

from cascade.application.contracts.commands import (
    ChangeCompatibilityModeCommand,
    CheckCompatibilityCommand,
    DeprecateVersionCommand,
    FieldInput,
    PublishSchemaVersionCommand,
    RegisterContractCommand,
    SchemaInput,
)
from cascade.application.contracts.queries import (
    GetContractQuery,
    GetSchemaVersionQuery,
    ListContractsQuery,
)
from cascade.infrastructure.cache.base import IdempotentResponse
from cascade.infrastructure.security.jwt import Principal
from cascade.presentation.api.dependencies import CacheDep, ContractServiceDep, SettingsDep
from cascade.presentation.api.schemas.common import PageMeta, PaginatedResponse
from cascade.presentation.api.schemas.contracts import (
    ChangeCompatibilityModeRequest,
    CheckCompatibilityRequest,
    CompatibilityReportResponse,
    ContractResponse,
    PublishVersionRequest,
    RegisterContractRequest,
    SchemaPayload,
    SchemaVersionResponse,
)
from cascade.presentation.api.security import require_scopes

router = APIRouter(prefix="/api/v1/contracts", tags=["contracts"])

WriteScope = Annotated[Principal, Depends(require_scopes("contracts:write"))]
ReadScope = Annotated[Principal, Depends(require_scopes("contracts:read"))]


@router.post(
    "",
    response_model=ContractResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a data contract",
)
async def register_contract(
    payload: RegisterContractRequest,
    service: ContractServiceDep,
    cache: CacheDep,
    settings: SettingsDep,
    principal: WriteScope,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    scoped_key = (
        f"contracts:register:{principal.subject}:{idempotency_key}" if idempotency_key else None
    )
    if scoped_key is not None:
        replayed = await cache.get_idempotent(scoped_key)
        if replayed is not None:
            return JSONResponse(status_code=replayed.status_code, content=json.loads(replayed.body))

    command = RegisterContractCommand(
        name=payload.name,
        schema_format=payload.schema_format,
        compatibility_mode=payload.compatibility_mode,
        schema=_to_schema_input(payload.schema_definition),
        description=payload.description,
    )
    view = await service.register_contract(command)
    body = ContractResponse.from_view(view).model_dump(mode="json")

    if scoped_key is not None:
        await cache.store_idempotent(
            scoped_key,
            IdempotentResponse(status_code=status.HTTP_201_CREATED, body=json.dumps(body)),
            settings.idempotency_ttl_seconds,
        )
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body)


@router.get("", response_model=PaginatedResponse[ContractResponse], summary="List contracts")
async def list_contracts(
    service: ContractServiceDep,
    _principal: ReadScope,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[str, Query()] = "created_at",
    descending: Annotated[bool, Query()] = True,
) -> PaginatedResponse[ContractResponse]:
    result = await service.list_contracts(
        ListContractsQuery(
            status=status_filter, page=page, size=size, sort_by=sort_by, descending=descending
        )
    )
    return PaginatedResponse[ContractResponse](
        items=[ContractResponse.from_view(item) for item in result.items],
        meta=PageMeta(page=result.page, size=result.size, total=result.total, pages=result.pages),
    )


@router.get("/{contract_id}", response_model=ContractResponse, summary="Get a contract")
async def get_contract(
    service: ContractServiceDep,
    _principal: ReadScope,
    contract_id: Annotated[str, Path()],
) -> ContractResponse:
    view = await service.get_contract(GetContractQuery(contract_id=contract_id))
    return ContractResponse.from_view(view)


@router.get(
    "/{contract_id}/versions/{version}",
    response_model=SchemaVersionResponse,
    summary="Get a schema version",
)
async def get_version(
    service: ContractServiceDep,
    _principal: ReadScope,
    contract_id: Annotated[str, Path()],
    version: Annotated[int, Path(ge=1)],
) -> SchemaVersionResponse:
    view = await service.get_version(
        GetSchemaVersionQuery(contract_id=contract_id, version=version)
    )
    return SchemaVersionResponse.from_view(view)


@router.post(
    "/{contract_id}/versions",
    response_model=SchemaVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a new schema version",
)
async def publish_version(
    payload: PublishVersionRequest,
    service: ContractServiceDep,
    _principal: WriteScope,
    contract_id: Annotated[str, Path()],
) -> SchemaVersionResponse:
    view = await service.publish_version(
        PublishSchemaVersionCommand(
            contract_id=contract_id, schema=_to_schema_input(payload.schema_definition)
        )
    )
    return SchemaVersionResponse.from_view(view)


@router.post(
    "/{contract_id}/compatibility",
    response_model=CompatibilityReportResponse,
    summary="Check a candidate schema for compatibility (dry run)",
)
async def check_compatibility(
    payload: CheckCompatibilityRequest,
    service: ContractServiceDep,
    _principal: ReadScope,
    contract_id: Annotated[str, Path()],
) -> CompatibilityReportResponse:
    view = await service.check_compatibility(
        CheckCompatibilityCommand(
            contract_id=contract_id, schema=_to_schema_input(payload.schema_definition)
        )
    )
    return CompatibilityReportResponse.from_view(view)


@router.put(
    "/{contract_id}/compatibility-mode",
    response_model=ContractResponse,
    summary="Change the compatibility mode",
)
async def change_compatibility_mode(
    payload: ChangeCompatibilityModeRequest,
    service: ContractServiceDep,
    _principal: WriteScope,
    contract_id: Annotated[str, Path()],
) -> ContractResponse:
    view = await service.change_compatibility_mode(
        ChangeCompatibilityModeCommand(
            contract_id=contract_id, compatibility_mode=payload.compatibility_mode
        )
    )
    return ContractResponse.from_view(view)


@router.post(
    "/{contract_id}/versions/{version}/deprecate",
    response_model=ContractResponse,
    summary="Deprecate a schema version",
)
async def deprecate_version(
    service: ContractServiceDep,
    _principal: WriteScope,
    contract_id: Annotated[str, Path()],
    version: Annotated[int, Path(ge=1)],
) -> ContractResponse:
    view = await service.deprecate_version(
        DeprecateVersionCommand(contract_id=contract_id, version=version)
    )
    return ContractResponse.from_view(view)


@router.post(
    "/{contract_id}/deprecate", response_model=ContractResponse, summary="Deprecate a contract"
)
async def deprecate_contract(
    service: ContractServiceDep,
    _principal: WriteScope,
    contract_id: Annotated[str, Path()],
) -> ContractResponse:
    view = await service.deprecate_contract(contract_id)
    return ContractResponse.from_view(view)


def _to_schema_input(payload: SchemaPayload) -> SchemaInput:
    return SchemaInput(
        fields=[
            FieldInput(
                name=f.name,
                type=f.type,
                nullable=f.nullable,
                has_default=f.has_default,
                doc=f.doc,
            )
            for f in payload.fields
        ]
    )
