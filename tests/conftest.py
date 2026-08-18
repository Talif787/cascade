from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.application.common.unit_of_work import UnitOfWork
from cascade.application.contracts.registry import RegistrationResult, SchemaRegistry
from cascade.application.governance.cost_source import CostObservation, CostSource
from cascade.application.ingestion.runtime import (
    ConnectorHandle,
    ConnectorRuntime,
    ConnectorSpec,
)
from cascade.application.lakehouse.orchestration import Orchestrator, ScheduleState
from cascade.application.lakehouse.transformation import (
    QualityOutcomeDTO,
    TransformationResult,
    TransformationRuntime,
    TransformationSpec,
)
from cascade.application.processing.runtime import (
    FlinkRuntime,
    JobHandle,
    JobSpec,
)
from cascade.domain.contracts.aggregate import DataContract
from cascade.domain.contracts.entities import SchemaVersion
from cascade.domain.contracts.repository import (
    ContractSortField,
    DataContractQuery,
    DataContractRepository,
)
from cascade.domain.contracts.value_objects import (
    ContractName,
    DataContractId,
    SchemaDefinition,
    SchemaFormat,
)
from cascade.domain.governance.aggregate import ServiceLevelObjective
from cascade.domain.governance.aggregate_cost import CostEntry
from cascade.domain.governance.repository import (
    CostEntryRepository,
    CostSummary,
    CostSummaryLine,
    SloQuery,
    SloRepository,
    SloSortField,
)
from cascade.domain.governance.value_objects import (
    AssetRef,
    CostEntryId,
    SloId,
    SloName,
    SloStatus,
)
from cascade.domain.ingestion.aggregate import IngestionSource
from cascade.domain.ingestion.repository import (
    IngestionSourceQuery,
    IngestionSourceRepository,
    SourceSortField,
)
from cascade.domain.ingestion.value_objects import IngestionSourceId, SourceName
from cascade.domain.lakehouse.aggregate import Dataset
from cascade.domain.lakehouse.repository import (
    DatasetQuery,
    DatasetRepository,
    DatasetSortField,
)
from cascade.domain.lakehouse.value_objects import DatasetId, DatasetName
from cascade.domain.pipelines.aggregate import Pipeline
from cascade.domain.pipelines.repository import (
    PipelineQuery,
    PipelineRepository,
    PipelineSortField,
)
from cascade.domain.pipelines.value_objects import PipelineId, PipelineName
from cascade.domain.processing.aggregate import StreamJob
from cascade.domain.processing.repository import (
    JobSortField,
    StreamJobQuery,
    StreamJobRepository,
)
from cascade.domain.processing.value_objects import JobName, StreamJobId
from cascade.domain.serving.aggregate import ServingView
from cascade.domain.serving.repository import (
    ServingViewQuery,
    ServingViewRepository,
    ServingViewSortField,
)
from cascade.domain.serving.value_objects import (
    ServingStatus,
    ServingViewId,
    ServingViewName,
)
from cascade.infrastructure.cache.base import Cache, IdempotentResponse, RateLimitDecision
from cascade.infrastructure.clickhouse.in_memory import InMemoryClickHouseRuntime
from cascade.infrastructure.config import Environment, Settings
from cascade.infrastructure.security.jwt import Principal, TokenVerifier
from cascade.presentation.api.app import AppComponents, create_app

_SORT_KEYS = {
    PipelineSortField.NAME: lambda p: str(p.name),
    PipelineSortField.STATUS: lambda p: p.status.value,
    PipelineSortField.CREATED_AT: lambda p: p.created_at,
    PipelineSortField.UPDATED_AT: lambda p: p.updated_at,
}

_CONTRACT_SORT_KEYS = {
    ContractSortField.NAME: lambda c: str(c.name),
    ContractSortField.STATUS: lambda c: c.status.value,
    ContractSortField.CREATED_AT: lambda c: c.created_at,
    ContractSortField.UPDATED_AT: lambda c: c.updated_at,
}

_SOURCE_SORT_KEYS = {
    SourceSortField.NAME: lambda s: str(s.name),
    SourceSortField.STATUS: lambda s: s.status.value,
    SourceSortField.CREATED_AT: lambda s: s.created_at,
    SourceSortField.UPDATED_AT: lambda s: s.updated_at,
}

_JOB_SORT_KEYS = {
    JobSortField.NAME: lambda j: str(j.name),
    JobSortField.STATUS: lambda j: j.status.value,
    JobSortField.CREATED_AT: lambda j: j.created_at,
    JobSortField.UPDATED_AT: lambda j: j.updated_at,
}

_DATASET_SORT_KEYS = {
    DatasetSortField.NAME: lambda d: str(d.name),
    DatasetSortField.LAYER: lambda d: d.layer.value,
    DatasetSortField.STATUS: lambda d: d.status.value,
    DatasetSortField.CREATED_AT: lambda d: d.created_at,
    DatasetSortField.UPDATED_AT: lambda d: d.updated_at,
}

_SERVING_SORT_KEYS = {
    ServingViewSortField.NAME: lambda v: str(v.name),
    ServingViewSortField.STATUS: lambda v: v.status.value,
    ServingViewSortField.CREATED_AT: lambda v: v.created_at,
    ServingViewSortField.UPDATED_AT: lambda v: v.updated_at,
}

_SLO_SORT_KEYS = {
    SloSortField.NAME: lambda s: str(s.name),
    SloSortField.STATUS: lambda s: s.status.value,
    SloSortField.STATE: lambda s: s.state.value,
    SloSortField.CREATED_AT: lambda s: s.created_at,
    SloSortField.UPDATED_AT: lambda s: s.updated_at,
}


def _clone(pipeline: Pipeline) -> Pipeline:
    return Pipeline(
        pipeline.id,
        name=pipeline.name,
        source=pipeline.source,
        sink=pipeline.sink,
        status=pipeline.status,
        description=pipeline.description,
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
        version=pipeline.version,
    )


class InMemoryPipelineRepository(PipelineRepository):
    def __init__(self, store: dict[uuid.UUID, Pipeline]) -> None:
        self._store = store

    async def add(self, pipeline: Pipeline) -> None:
        if any(str(p.name) == str(pipeline.name) for p in self._store.values()):
            raise ConflictError(f"pipeline name {pipeline.name!s} is already in use")
        self._store[pipeline.id.value] = _clone(pipeline)

    async def update(self, pipeline: Pipeline) -> None:
        current = self._store.get(pipeline.id.value)
        if current is None or current.version != pipeline.version:
            raise ConcurrencyError(f"pipeline {pipeline.id!s} was modified concurrently")
        new_version = pipeline.version + 1
        pipeline._version = new_version
        self._store[pipeline.id.value] = _clone(pipeline)

    async def get(self, pipeline_id: PipelineId) -> Pipeline | None:
        found = self._store.get(pipeline_id.value)
        return _clone(found) if found is not None else None

    async def get_by_name(self, name: PipelineName) -> Pipeline | None:
        for pipeline in self._store.values():
            if str(pipeline.name) == str(name):
                return _clone(pipeline)
        return None

    async def exists_by_name(self, name: PipelineName) -> bool:
        return any(str(p.name) == str(name) for p in self._store.values())

    async def list(self, query: PipelineQuery) -> tuple[list[Pipeline], int]:
        items = list(self._store.values())
        if query.status is not None:
            items = [p for p in items if p.status == query.status]
        items.sort(key=_SORT_KEYS[query.sort_by], reverse=query.descending)
        total = len(items)
        window = items[query.offset : query.offset + query.limit]
        return [_clone(p) for p in window], total


class InMemoryUnitOfWork(UnitOfWork):
    def __init__(
        self,
        pipeline_store: dict[uuid.UUID, Pipeline],
        contract_store: dict[uuid.UUID, DataContract],
        source_store: dict[uuid.UUID, IngestionSource] | None = None,
        job_store: dict[uuid.UUID, StreamJob] | None = None,
        dataset_store: dict[uuid.UUID, Dataset] | None = None,
        serving_store: dict[uuid.UUID, ServingView] | None = None,
        slo_store: dict[uuid.UUID, ServiceLevelObjective] | None = None,
        cost_store: dict[uuid.UUID, CostEntry] | None = None,
    ) -> None:
        self._pipeline_store = pipeline_store
        self._contract_store = contract_store
        self._source_store = source_store if source_store is not None else {}
        self._job_store = job_store if job_store is not None else {}
        self._dataset_store = dataset_store if dataset_store is not None else {}
        self._serving_store = serving_store if serving_store is not None else {}
        self._slo_store = slo_store if slo_store is not None else {}
        self._cost_store = cost_store if cost_store is not None else {}

    async def __aenter__(self) -> InMemoryUnitOfWork:
        self.pipelines = InMemoryPipelineRepository(self._pipeline_store)
        self.contracts = InMemoryDataContractRepository(self._contract_store)
        self.ingestion_sources = InMemoryIngestionSourceRepository(self._source_store)
        self.stream_jobs = InMemoryStreamJobRepository(self._job_store)
        self.datasets = InMemoryDatasetRepository(self._dataset_store)
        self.serving_views = InMemoryServingViewRepository(self._serving_store)
        self.slos = InMemorySloRepository(self._slo_store)
        self.cost_entries = InMemoryCostEntryRepository(self._cost_store)
        return self

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


def _clone_contract(contract: DataContract) -> DataContract:
    versions = [
        SchemaVersion(
            version=v.version,
            schema=v.schema,
            status=v.status,
            created_at=v.created_at,
            registry_id=v.registry_id,
        )
        for v in contract.versions
    ]
    return DataContract(
        contract.id,
        name=contract.name,
        schema_format=contract.schema_format,
        compatibility_mode=contract.compatibility_mode,
        status=contract.status,
        description=contract.description,
        versions=versions,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        version=contract.version,
    )


class InMemoryDataContractRepository(DataContractRepository):
    def __init__(self, store: dict[uuid.UUID, DataContract]) -> None:
        self._store = store

    async def add(self, contract: DataContract) -> None:
        if any(str(c.name) == str(contract.name) for c in self._store.values()):
            raise ConflictError(f"contract name {contract.name!s} is already in use")
        self._store[contract.id.value] = _clone_contract(contract)

    async def update(self, contract: DataContract) -> None:
        current = self._store.get(contract.id.value)
        if current is None or current.version != contract.version:
            raise ConcurrencyError(f"contract {contract.id!s} was modified concurrently")
        contract._version = contract.version + 1
        self._store[contract.id.value] = _clone_contract(contract)

    async def get(self, contract_id: DataContractId) -> DataContract | None:
        found = self._store.get(contract_id.value)
        return _clone_contract(found) if found is not None else None

    async def get_by_name(self, name: ContractName) -> DataContract | None:
        for contract in self._store.values():
            if str(contract.name) == str(name):
                return _clone_contract(contract)
        return None

    async def exists_by_name(self, name: ContractName) -> bool:
        return any(str(c.name) == str(name) for c in self._store.values())

    async def list(self, query: DataContractQuery) -> tuple[list[DataContract], int]:
        items = list(self._store.values())
        if query.status is not None:
            items = [c for c in items if c.status == query.status]
        items.sort(key=_CONTRACT_SORT_KEYS[query.sort_by], reverse=query.descending)
        total = len(items)
        window = items[query.offset : query.offset + query.limit]
        return [_clone_contract(c) for c in window], total


class FakeSchemaRegistry(SchemaRegistry):
    def __init__(self) -> None:
        self._next_id = 1

    async def register(
        self, subject: str, schema: SchemaDefinition, schema_format: SchemaFormat
    ) -> RegistrationResult:
        result = RegistrationResult(registry_id=self._next_id, subject=subject, version=1)
        self._next_id += 1
        return result

    async def ping(self) -> bool:
        return True


def _clone_source(source: IngestionSource) -> IngestionSource:
    return IngestionSource(
        source.id,
        name=source.name,
        connector_kind=source.connector_kind,
        config=source.config,
        contract_id=source.contract_id,
        pipeline_id=source.pipeline_id,
        status=source.status,
        dead_letter_policy=source.dead_letter_policy,
        dead_letter_count=source.dead_letter_count,
        runtime_ref=source.runtime_ref,
        description=source.description,
        created_at=source.created_at,
        updated_at=source.updated_at,
        version=source.version,
    )


class InMemoryIngestionSourceRepository(IngestionSourceRepository):
    def __init__(self, store: dict[uuid.UUID, IngestionSource]) -> None:
        self._store = store

    async def add(self, source: IngestionSource) -> None:
        if any(str(s.name) == str(source.name) for s in self._store.values()):
            raise ConflictError(f"source name {source.name!s} is already in use")
        self._store[source.id.value] = _clone_source(source)

    async def update(self, source: IngestionSource) -> None:
        current = self._store.get(source.id.value)
        if current is None or current.version != source.version:
            raise ConcurrencyError(f"source {source.id!s} was modified concurrently")
        source._version = source.version + 1
        self._store[source.id.value] = _clone_source(source)

    async def get(self, source_id: IngestionSourceId) -> IngestionSource | None:
        found = self._store.get(source_id.value)
        return _clone_source(found) if found is not None else None

    async def get_by_name(self, name: SourceName) -> IngestionSource | None:
        for source in self._store.values():
            if str(source.name) == str(name):
                return _clone_source(source)
        return None

    async def exists_by_name(self, name: SourceName) -> bool:
        return any(str(s.name) == str(name) for s in self._store.values())

    async def list(self, query: IngestionSourceQuery) -> tuple[list[IngestionSource], int]:
        items = list(self._store.values())
        if query.status is not None:
            items = [s for s in items if s.status == query.status]
        if query.connector_kind is not None:
            items = [s for s in items if s.connector_kind == query.connector_kind]
        if query.contract_id is not None:
            items = [s for s in items if s.contract_id == query.contract_id]
        items.sort(key=_SOURCE_SORT_KEYS[query.sort_by], reverse=query.descending)
        total = len(items)
        window = items[query.offset : query.offset + query.limit]
        return [_clone_source(s) for s in window], total


class FakeConnectorRuntime(ConnectorRuntime):
    def __init__(self, fail_on_deploy: bool = False) -> None:
        self.fail_on_deploy = fail_on_deploy
        self.deployed: dict[str, str] = {}

    async def deploy(self, spec: ConnectorSpec) -> ConnectorHandle:
        if self.fail_on_deploy:
            from cascade.application.ingestion.runtime import ConnectorRuntimeError

            raise ConnectorRuntimeError("deploy rejected")
        self.deployed[spec.name] = "RUNNING"
        return ConnectorHandle(name=spec.name, state="RUNNING")

    async def pause(self, name: str) -> None:
        self.deployed[name] = "PAUSED"

    async def resume(self, name: str) -> None:
        self.deployed[name] = "RUNNING"

    async def delete(self, name: str) -> None:
        self.deployed.pop(name, None)

    async def status(self, name: str) -> ConnectorHandle | None:
        state = self.deployed.get(name)
        return ConnectorHandle(name=name, state=state) if state is not None else None


def _clone_job(job: StreamJob) -> StreamJob:
    return StreamJob(
        job.id,
        name=job.name,
        source=job.source,
        sink=job.sink,
        delivery_guarantee=job.delivery_guarantee,
        checkpoint_config=job.checkpoint_config,
        restart_strategy=job.restart_strategy,
        parallelism=job.parallelism,
        contract_id=job.contract_id,
        status=job.status,
        runtime_ref=job.runtime_ref,
        savepoint_location=job.savepoint_location,
        description=job.description,
        created_at=job.created_at,
        updated_at=job.updated_at,
        version=job.version,
    )


class InMemoryStreamJobRepository(StreamJobRepository):
    def __init__(self, store: dict[uuid.UUID, StreamJob]) -> None:
        self._store = store

    async def add(self, job: StreamJob) -> None:
        if any(str(j.name) == str(job.name) for j in self._store.values()):
            raise ConflictError(f"job name {job.name!s} is already in use")
        self._store[job.id.value] = _clone_job(job)

    async def update(self, job: StreamJob) -> None:
        current = self._store.get(job.id.value)
        if current is None or current.version != job.version:
            raise ConcurrencyError(f"job {job.id!s} was modified concurrently")
        job._version = job.version + 1
        self._store[job.id.value] = _clone_job(job)

    async def get(self, job_id: StreamJobId) -> StreamJob | None:
        found = self._store.get(job_id.value)
        return _clone_job(found) if found is not None else None

    async def get_by_name(self, name: JobName) -> StreamJob | None:
        for job in self._store.values():
            if str(job.name) == str(name):
                return _clone_job(job)
        return None

    async def exists_by_name(self, name: JobName) -> bool:
        return any(str(j.name) == str(name) for j in self._store.values())

    async def list(self, query: StreamJobQuery) -> tuple[list[StreamJob], int]:
        items = list(self._store.values())
        if query.status is not None:
            items = [j for j in items if j.status == query.status]
        if query.sink_kind is not None:
            items = [j for j in items if j.sink.kind == query.sink_kind]
        if query.delivery_guarantee is not None:
            items = [j for j in items if j.delivery_guarantee == query.delivery_guarantee]
        if query.contract_id is not None:
            items = [j for j in items if j.contract_id == query.contract_id]
        items.sort(key=_JOB_SORT_KEYS[query.sort_by], reverse=query.descending)
        total = len(items)
        window = items[query.offset : query.offset + query.limit]
        return [_clone_job(j) for j in window], total


class FakeFlinkRuntime(FlinkRuntime):
    def __init__(self, fail_on_submit: bool = False) -> None:
        self.fail_on_submit = fail_on_submit
        self.jobs: dict[str, str] = {}
        self._counter = 0

    async def submit(self, spec: JobSpec) -> JobHandle:
        if self.fail_on_submit:
            from cascade.application.processing.runtime import FlinkRuntimeError

            raise FlinkRuntimeError("submit rejected")
        self._counter += 1
        job_id = f"flink-job-{self._counter}"
        self.jobs[job_id] = "RUNNING"
        return JobHandle(job_id=job_id, state="RUNNING")

    async def stop_with_savepoint(self, job_id: str) -> str:
        self.jobs[job_id] = "FINISHED"
        return f"s3://savepoints/{job_id}/sp-1"

    async def trigger_savepoint(self, job_id: str) -> str:
        return f"s3://savepoints/{job_id}/sp-adhoc"

    async def cancel(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)

    async def status(self, job_id: str) -> JobHandle | None:
        state = self.jobs.get(job_id)
        return JobHandle(job_id=job_id, state=state) if state is not None else None


def _clone_dataset(dataset: Dataset) -> Dataset:
    return Dataset(
        dataset.id,
        name=dataset.name,
        layer=dataset.layer,
        transformation=dataset.transformation,
        upstreams=dataset.upstreams,
        schedule=dataset.schedule,
        quality_checks=dataset.quality_checks,
        contract_id=dataset.contract_id,
        status=dataset.status,
        quality_status=dataset.quality_status,
        last_run_ref=dataset.last_run_ref,
        last_row_count=dataset.last_row_count,
        last_materialized_at=dataset.last_materialized_at,
        last_quality_outcomes=dataset.last_quality_outcomes,
        description=dataset.description,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        version=dataset.version,
    )


class InMemoryDatasetRepository(DatasetRepository):
    def __init__(self, store: dict[uuid.UUID, Dataset]) -> None:
        self._store = store

    async def add(self, dataset: Dataset) -> None:
        if any(str(d.name) == str(dataset.name) for d in self._store.values()):
            raise ConflictError(f"dataset name {dataset.name!s} is already in use")
        self._store[dataset.id.value] = _clone_dataset(dataset)

    async def update(self, dataset: Dataset) -> None:
        current = self._store.get(dataset.id.value)
        if current is None or current.version != dataset.version:
            raise ConcurrencyError(f"dataset {dataset.id!s} was modified concurrently")
        dataset._version = dataset.version + 1
        self._store[dataset.id.value] = _clone_dataset(dataset)

    async def get(self, dataset_id: DatasetId) -> Dataset | None:
        found = self._store.get(dataset_id.value)
        return _clone_dataset(found) if found is not None else None

    async def get_by_name(self, name: DatasetName) -> Dataset | None:
        for dataset in self._store.values():
            if str(dataset.name) == str(name):
                return _clone_dataset(dataset)
        return None

    async def exists_by_name(self, name: DatasetName) -> bool:
        return any(str(d.name) == str(name) for d in self._store.values())

    async def list(self, query: DatasetQuery) -> tuple[list[Dataset], int]:
        items = list(self._store.values())
        if query.layer is not None:
            items = [d for d in items if d.layer == query.layer]
        if query.status is not None:
            items = [d for d in items if d.status == query.status]
        if query.quality_status is not None:
            items = [d for d in items if d.quality_status == query.quality_status]
        if query.contract_id is not None:
            items = [d for d in items if d.contract_id == query.contract_id]
        items.sort(key=_DATASET_SORT_KEYS[query.sort_by], reverse=query.descending)
        total = len(items)
        window = items[query.offset : query.offset + query.limit]
        return [_clone_dataset(d) for d in window], total

    async def list_dependents(self, dataset_id: DatasetId) -> list[Dataset]:
        return [_clone_dataset(d) for d in self._store.values() if d.depends_on(dataset_id)]


class FakeTransformationRuntime(TransformationRuntime):
    def __init__(self, fail: bool = False, row_count: int = 1000) -> None:
        self.fail = fail
        self.row_count = row_count

    async def run(self, spec: TransformationSpec) -> TransformationResult:
        if self.fail:
            from cascade.application.lakehouse.transformation import (
                TransformationRuntimeError,
            )

            raise TransformationRuntimeError("run rejected")
        outcomes = tuple(
            QualityOutcomeDTO(name=check.name, passed=check.column != "force_fail")
            for check in spec.quality_checks
        )
        return TransformationResult(
            run_ref="dbt-run-test", row_count=self.row_count, quality=outcomes
        )


class FakeOrchestrator(Orchestrator):
    def __init__(self) -> None:
        self.schedules: dict[str, bool] = {}

    async def upsert_schedule(self, dag_id: str, cron: str, timezone: str, enabled: bool) -> None:
        self.schedules[dag_id] = enabled

    async def trigger(self, dag_id: str) -> str:
        return "manual__test"

    async def pause(self, dag_id: str) -> None:
        if dag_id in self.schedules:
            self.schedules[dag_id] = False

    async def status(self, dag_id: str) -> ScheduleState | None:
        if dag_id not in self.schedules:
            return None
        return ScheduleState(dag_id=dag_id, enabled=self.schedules[dag_id])


def _clone_serving_view(view: ServingView) -> ServingView:
    return ServingView(
        view.id,
        name=view.name,
        source_dataset_id=view.source_dataset_id,
        engine=view.engine,
        schema=view.schema,
        refresh_mode=view.refresh_mode,
        refresh_cron=view.refresh_cron,
        refresh_enabled=view.refresh_enabled,
        status=view.status,
        last_sync_ref=view.last_sync_ref,
        last_row_count=view.last_row_count,
        last_synced_at=view.last_synced_at,
        synced_source_at=view.synced_source_at,
        description=view.description,
        created_at=view.created_at,
        updated_at=view.updated_at,
        version=view.version,
    )


class InMemoryServingViewRepository(ServingViewRepository):
    def __init__(self, store: dict[uuid.UUID, ServingView]) -> None:
        self._store = store

    async def add(self, view: ServingView) -> None:
        if any(str(v.name) == str(view.name) for v in self._store.values()):
            raise ConflictError(f"serving view name {view.name!s} is already in use")
        self._store[view.id.value] = _clone_serving_view(view)

    async def update(self, view: ServingView) -> None:
        current = self._store.get(view.id.value)
        if current is None or current.version != view.version:
            raise ConcurrencyError(f"serving view {view.id!s} was modified concurrently")
        view._version = view.version + 1
        self._store[view.id.value] = _clone_serving_view(view)

    async def get(self, view_id: ServingViewId) -> ServingView | None:
        found = self._store.get(view_id.value)
        return _clone_serving_view(found) if found is not None else None

    async def get_by_name(self, name: ServingViewName) -> ServingView | None:
        for view in self._store.values():
            if str(view.name) == str(name):
                return _clone_serving_view(view)
        return None

    async def exists_by_name(self, name: ServingViewName) -> bool:
        return any(str(v.name) == str(name) for v in self._store.values())

    async def list(self, query: ServingViewQuery) -> tuple[list[ServingView], int]:
        items = list(self._store.values())
        if query.status is not None:
            items = [v for v in items if v.status == query.status]
        if query.engine is not None:
            items = [v for v in items if v.engine == query.engine]
        if query.source_dataset_id is not None:
            items = [v for v in items if v.source_dataset_id == query.source_dataset_id]
        items.sort(key=_SERVING_SORT_KEYS[query.sort_by], reverse=query.descending)
        total = len(items)
        window = items[query.offset : query.offset + query.limit]
        return [_clone_serving_view(v) for v in window], total

    async def list_ready(self) -> Sequence[ServingView]:
        ready = [
            _clone_serving_view(v) for v in self._store.values() if v.status is ServingStatus.READY
        ]
        ready.sort(key=lambda v: str(v.name))
        return ready


def _clone_slo(slo: ServiceLevelObjective) -> ServiceLevelObjective:
    return ServiceLevelObjective(
        slo.id,
        name=slo.name,
        asset=slo.asset,
        target=slo.target,
        severity=slo.severity,
        owner=slo.owner,
        description=slo.description,
        status=slo.status,
        state=slo.state,
        last_evaluated_at=slo.last_evaluated_at,
        last_staleness_minutes=slo.last_staleness_minutes,
        breach_count=slo.breach_count,
        created_at=slo.created_at,
        updated_at=slo.updated_at,
        version=slo.version,
    )


class InMemorySloRepository(SloRepository):
    def __init__(self, store: dict[uuid.UUID, ServiceLevelObjective]) -> None:
        self._store = store

    async def add(self, slo: ServiceLevelObjective) -> None:
        if any(str(s.name) == str(slo.name) for s in self._store.values()):
            raise ConflictError(f"SLO name {slo.name!s} is already in use")
        self._store[slo.id.value] = _clone_slo(slo)

    async def update(self, slo: ServiceLevelObjective) -> None:
        current = self._store.get(slo.id.value)
        if current is None or current.version != slo.version:
            raise ConcurrencyError(f"SLO {slo.id!s} was modified concurrently")
        slo._version = slo.version + 1
        self._store[slo.id.value] = _clone_slo(slo)

    async def get(self, slo_id: SloId) -> ServiceLevelObjective | None:
        found = self._store.get(slo_id.value)
        return _clone_slo(found) if found is not None else None

    async def get_by_name(self, name: SloName) -> ServiceLevelObjective | None:
        for slo in self._store.values():
            if str(slo.name) == str(name):
                return _clone_slo(slo)
        return None

    async def exists_by_name(self, name: SloName) -> bool:
        return any(str(s.name) == str(name) for s in self._store.values())

    async def list(self, query: SloQuery) -> tuple[list[ServiceLevelObjective], int]:
        items = list(self._store.values())
        if query.asset_kind is not None:
            items = [s for s in items if s.asset.kind == query.asset_kind]
        if query.status is not None:
            items = [s for s in items if s.status == query.status]
        if query.state is not None:
            items = [s for s in items if s.state == query.state]
        items.sort(key=_SLO_SORT_KEYS[query.sort_by], reverse=query.descending)
        total = len(items)
        window = items[query.offset : query.offset + query.limit]
        return [_clone_slo(s) for s in window], total

    async def list_active(self) -> Sequence[ServiceLevelObjective]:
        active = [_clone_slo(s) for s in self._store.values() if s.status is SloStatus.ACTIVE]
        active.sort(key=lambda s: str(s.name))
        return active


class InMemoryCostEntryRepository(CostEntryRepository):
    def __init__(self, store: dict[uuid.UUID, CostEntry]) -> None:
        self._store = store

    async def add(self, entry: CostEntry) -> None:
        self._store[entry.id.value] = entry

    async def get(self, entry_id: CostEntryId) -> CostEntry | None:
        return self._store.get(entry_id.value)

    async def list_for_asset(self, asset: AssetRef) -> Sequence[CostEntry]:
        return [
            e
            for e in self._store.values()
            if e.asset.kind == asset.kind and e.asset.asset_id == asset.asset_id
        ]

    async def summarize(
        self, window_start: datetime | None, window_end: datetime | None
    ) -> CostSummary:
        entries = list(self._store.values())
        if window_start is not None:
            entries = [e for e in entries if e.period.start >= window_start]
        if window_end is not None:
            entries = [e for e in entries if e.period.end <= window_end]
        total = sum(e.amount.amount_cents for e in entries)

        by_category: dict[str, int] = {}
        by_asset: dict[str, int] = {}
        for entry in entries:
            by_category[entry.category.value] = (
                by_category.get(entry.category.value, 0) + entry.amount.amount_cents
            )
            key = str(entry.asset)
            by_asset[key] = by_asset.get(key, 0) + entry.amount.amount_cents

        return CostSummary(
            total_cents=total,
            by_category=tuple(
                CostSummaryLine(key=k, amount_cents=v)
                for k, v in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
            ),
            by_asset=tuple(
                CostSummaryLine(key=k, amount_cents=v)
                for k, v in sorted(by_asset.items(), key=lambda kv: kv[1], reverse=True)
            ),
        )


class FakeCostSource(CostSource):
    def __init__(self, observations: tuple[CostObservation, ...] = ()) -> None:
        self.observations = observations

    async def fetch(
        self, window_start: datetime, window_end: datetime
    ) -> tuple[CostObservation, ...]:
        return self.observations


class FakeCache(Cache):
    def __init__(self) -> None:
        self._idempotency: dict[str, IdempotentResponse] = {}

    async def ping(self) -> bool:
        return True

    async def get_idempotent(self, key: str) -> IdempotentResponse | None:
        return self._idempotency.get(key)

    async def store_idempotent(
        self, key: str, response: IdempotentResponse, ttl_seconds: int
    ) -> None:
        self._idempotency.setdefault(key, response)

    async def check_rate_limit(
        self, identity: str, *, rate_per_second: float, burst: int
    ) -> RateLimitDecision:
        return RateLimitDecision(allowed=True, retry_after_seconds=0)


class StaticTokenVerifier(TokenVerifier):
    def verify(self, token: str) -> Principal:
        return Principal(
            subject="test-user",
            scopes=frozenset(
                {
                    "pipelines:read",
                    "pipelines:write",
                    "contracts:read",
                    "contracts:write",
                    "ingestion:read",
                    "ingestion:write",
                    "processing:read",
                    "processing:write",
                    "lakehouse:read",
                    "lakehouse:write",
                    "serving:read",
                    "serving:write",
                    "governance:read",
                    "governance:write",
                }
            ),
        )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment=Environment.LOCAL,
        log_json=False,
        auth_enabled=True,
        rate_limit_enabled=False,
        otel_enabled=False,
    )


@pytest.fixture
def store() -> dict[uuid.UUID, Pipeline]:
    return {}


@pytest.fixture
def contract_store() -> dict[uuid.UUID, DataContract]:
    return {}


@pytest.fixture
def source_store() -> dict[uuid.UUID, IngestionSource]:
    return {}


@pytest.fixture
def job_store() -> dict[uuid.UUID, StreamJob]:
    return {}


@pytest.fixture
def dataset_store() -> dict[uuid.UUID, Dataset]:
    return {}


@pytest.fixture
def serving_store() -> dict[uuid.UUID, ServingView]:
    return {}


@pytest.fixture
def slo_store() -> dict[uuid.UUID, ServiceLevelObjective]:
    return {}


@pytest.fixture
def cost_store() -> dict[uuid.UUID, CostEntry]:
    return {}


@pytest.fixture
def connector_runtime() -> FakeConnectorRuntime:
    return FakeConnectorRuntime()


@pytest.fixture
def flink_runtime() -> FakeFlinkRuntime:
    return FakeFlinkRuntime()


@pytest.fixture
def transformation_runtime() -> FakeTransformationRuntime:
    return FakeTransformationRuntime()


@pytest.fixture
def orchestrator() -> FakeOrchestrator:
    return FakeOrchestrator()


@pytest.fixture
def clickhouse_runtime() -> InMemoryClickHouseRuntime:
    return InMemoryClickHouseRuntime()


@pytest.fixture
def cost_source() -> FakeCostSource:
    return FakeCostSource()


@pytest.fixture
def cache() -> FakeCache:
    return FakeCache()


@pytest.fixture
def components(
    store: dict[uuid.UUID, Pipeline],
    contract_store: dict[uuid.UUID, DataContract],
    source_store: dict[uuid.UUID, IngestionSource],
    job_store: dict[uuid.UUID, StreamJob],
    dataset_store: dict[uuid.UUID, Dataset],
    serving_store: dict[uuid.UUID, ServingView],
    slo_store: dict[uuid.UUID, ServiceLevelObjective],
    cost_store: dict[uuid.UUID, CostEntry],
    connector_runtime: FakeConnectorRuntime,
    flink_runtime: FakeFlinkRuntime,
    transformation_runtime: FakeTransformationRuntime,
    orchestrator: FakeOrchestrator,
    clickhouse_runtime: InMemoryClickHouseRuntime,
    cost_source: FakeCostSource,
    cache: FakeCache,
) -> AppComponents:
    async def _ok() -> bool:
        return True

    return AppComponents(
        uow_factory=lambda: InMemoryUnitOfWork(
            store,
            contract_store,
            source_store,
            job_store,
            dataset_store,
            serving_store,
            slo_store,
            cost_store,
        ),
        cache=cache,
        token_verifier=StaticTokenVerifier(),
        schema_registry=FakeSchemaRegistry(),
        connector_runtime=connector_runtime,
        flink_runtime=flink_runtime,
        transformation_runtime=transformation_runtime,
        orchestrator=orchestrator,
        clickhouse_runtime=clickhouse_runtime,
        cost_source=cost_source,
        health_checks={"database": _ok, "redis": _ok},
    )


@pytest_asyncio.fixture
async def client(settings: Settings, components: AppComponents) -> AsyncIterator[AsyncClient]:
    app = create_app(settings, components)
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": "Bearer test-token"},
        ) as http_client,
    ):
        yield http_client


class ReadOnlyTokenVerifier(TokenVerifier):
    def verify(self, token: str) -> Principal:
        return Principal(
            subject="read-only-user",
            scopes=frozenset(
                {
                    "pipelines:read",
                    "contracts:read",
                    "ingestion:read",
                    "processing:read",
                    "lakehouse:read",
                    "serving:read",
                    "governance:read",
                }
            ),
        )


@pytest.fixture
def readonly_components(
    store: dict[uuid.UUID, Pipeline],
    contract_store: dict[uuid.UUID, DataContract],
    source_store: dict[uuid.UUID, IngestionSource],
    job_store: dict[uuid.UUID, StreamJob],
    dataset_store: dict[uuid.UUID, Dataset],
    serving_store: dict[uuid.UUID, ServingView],
    slo_store: dict[uuid.UUID, ServiceLevelObjective],
    cost_store: dict[uuid.UUID, CostEntry],
    connector_runtime: FakeConnectorRuntime,
    flink_runtime: FakeFlinkRuntime,
    transformation_runtime: FakeTransformationRuntime,
    orchestrator: FakeOrchestrator,
    clickhouse_runtime: InMemoryClickHouseRuntime,
    cost_source: FakeCostSource,
    cache: FakeCache,
) -> AppComponents:
    async def _ok() -> bool:
        return True

    return AppComponents(
        uow_factory=lambda: InMemoryUnitOfWork(
            store,
            contract_store,
            source_store,
            job_store,
            dataset_store,
            serving_store,
            slo_store,
            cost_store,
        ),
        cache=cache,
        token_verifier=ReadOnlyTokenVerifier(),
        schema_registry=FakeSchemaRegistry(),
        connector_runtime=connector_runtime,
        flink_runtime=flink_runtime,
        transformation_runtime=transformation_runtime,
        orchestrator=orchestrator,
        clickhouse_runtime=clickhouse_runtime,
        cost_source=cost_source,
        health_checks={"database": _ok, "redis": _ok},
    )


@pytest_asyncio.fixture
async def readonly_client(
    settings: Settings, readonly_components: AppComponents
) -> AsyncIterator[AsyncClient]:
    app = create_app(settings, readonly_components)
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": "Bearer test-token"},
        ) as http_client,
    ):
        yield http_client
