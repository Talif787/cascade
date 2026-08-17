from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from cascade.application.contracts.registry import SchemaRegistry
from cascade.application.contracts.service import DataContractApplicationService
from cascade.application.pipelines.service import PipelineApplicationService
from cascade.infrastructure.cache.base import Cache
from cascade.infrastructure.config import Settings


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_cache(request: Request) -> Cache:
    return cast(Cache, request.app.state.cache)


def get_schema_registry(request: Request) -> SchemaRegistry:
    return cast(SchemaRegistry, request.app.state.schema_registry)


def get_pipeline_service(request: Request) -> PipelineApplicationService:
    return PipelineApplicationService(request.app.state.uow_factory)


def get_contract_service(request: Request) -> DataContractApplicationService:
    return DataContractApplicationService(
        request.app.state.uow_factory, request.app.state.schema_registry
    )


SettingsDep = Annotated[Settings, Depends(get_settings)]
CacheDep = Annotated[Cache, Depends(get_cache)]
PipelineServiceDep = Annotated[PipelineApplicationService, Depends(get_pipeline_service)]
ContractServiceDep = Annotated[DataContractApplicationService, Depends(get_contract_service)]
