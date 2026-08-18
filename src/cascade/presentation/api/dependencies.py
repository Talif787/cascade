from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from cascade.application.contracts.registry import SchemaRegistry
from cascade.application.contracts.service import DataContractApplicationService
from cascade.application.governance.cost_source import CostSource
from cascade.application.governance.service import GovernanceApplicationService
from cascade.application.ingestion.runtime import ConnectorRuntime
from cascade.application.ingestion.service import IngestionApplicationService
from cascade.application.lakehouse.orchestration import Orchestrator
from cascade.application.lakehouse.service import LakehouseApplicationService
from cascade.application.lakehouse.transformation import TransformationRuntime
from cascade.application.pipelines.service import PipelineApplicationService
from cascade.application.processing.runtime import FlinkRuntime
from cascade.application.processing.service import StreamProcessingApplicationService
from cascade.application.serving.runtime import ClickHouseRuntime
from cascade.application.serving.service import ServingApplicationService
from cascade.infrastructure.cache.base import Cache
from cascade.infrastructure.config import Settings


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_cache(request: Request) -> Cache:
    return cast(Cache, request.app.state.cache)


def get_schema_registry(request: Request) -> SchemaRegistry:
    return cast(SchemaRegistry, request.app.state.schema_registry)


def get_connector_runtime(request: Request) -> ConnectorRuntime:
    return cast(ConnectorRuntime, request.app.state.connector_runtime)


def get_flink_runtime(request: Request) -> FlinkRuntime:
    return cast(FlinkRuntime, request.app.state.flink_runtime)


def get_transformation_runtime(request: Request) -> TransformationRuntime:
    return cast(TransformationRuntime, request.app.state.transformation_runtime)


def get_orchestrator(request: Request) -> Orchestrator:
    return cast(Orchestrator, request.app.state.orchestrator)


def get_clickhouse_runtime(request: Request) -> ClickHouseRuntime:
    return cast(ClickHouseRuntime, request.app.state.clickhouse_runtime)


def get_cost_source(request: Request) -> CostSource:
    return cast(CostSource, request.app.state.cost_source)


def get_pipeline_service(request: Request) -> PipelineApplicationService:
    return PipelineApplicationService(request.app.state.uow_factory)


def get_contract_service(request: Request) -> DataContractApplicationService:
    return DataContractApplicationService(
        request.app.state.uow_factory, request.app.state.schema_registry
    )


def get_ingestion_service(request: Request) -> IngestionApplicationService:
    return IngestionApplicationService(
        request.app.state.uow_factory, request.app.state.connector_runtime
    )


def get_processing_service(request: Request) -> StreamProcessingApplicationService:
    return StreamProcessingApplicationService(
        request.app.state.uow_factory, request.app.state.flink_runtime
    )


def get_lakehouse_service(request: Request) -> LakehouseApplicationService:
    return LakehouseApplicationService(
        request.app.state.uow_factory,
        request.app.state.transformation_runtime,
        request.app.state.orchestrator,
    )


def get_serving_service(request: Request) -> ServingApplicationService:
    return ServingApplicationService(
        request.app.state.uow_factory, request.app.state.clickhouse_runtime
    )


def get_governance_service(request: Request) -> GovernanceApplicationService:
    return GovernanceApplicationService(
        request.app.state.uow_factory, request.app.state.cost_source
    )


SettingsDep = Annotated[Settings, Depends(get_settings)]
CacheDep = Annotated[Cache, Depends(get_cache)]
PipelineServiceDep = Annotated[PipelineApplicationService, Depends(get_pipeline_service)]
ContractServiceDep = Annotated[DataContractApplicationService, Depends(get_contract_service)]
IngestionServiceDep = Annotated[IngestionApplicationService, Depends(get_ingestion_service)]
ProcessingServiceDep = Annotated[
    StreamProcessingApplicationService, Depends(get_processing_service)
]
LakehouseServiceDep = Annotated[LakehouseApplicationService, Depends(get_lakehouse_service)]
ServingServiceDep = Annotated[ServingApplicationService, Depends(get_serving_service)]
GovernanceServiceDep = Annotated[GovernanceApplicationService, Depends(get_governance_service)]
