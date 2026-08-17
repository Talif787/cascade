from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.application.common.unit_of_work import UnitOfWork
from cascade.application.contracts.registry import RegistrationResult, SchemaRegistry
from cascade.application.ingestion.runtime import (
    ConnectorHandle,
    ConnectorRuntime,
    ConnectorSpec,
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
from cascade.domain.ingestion.aggregate import IngestionSource
from cascade.domain.ingestion.repository import (
    IngestionSourceQuery,
    IngestionSourceRepository,
    SourceSortField,
)
from cascade.domain.ingestion.value_objects import IngestionSourceId, SourceName
from cascade.domain.pipelines.aggregate import Pipeline
from cascade.domain.pipelines.repository import (
    PipelineQuery,
    PipelineRepository,
    PipelineSortField,
)
from cascade.domain.pipelines.value_objects import PipelineId, PipelineName
from cascade.infrastructure.cache.base import Cache, IdempotentResponse, RateLimitDecision
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
    ) -> None:
        self._pipeline_store = pipeline_store
        self._contract_store = contract_store
        self._source_store = source_store if source_store is not None else {}

    async def __aenter__(self) -> InMemoryUnitOfWork:
        self.pipelines = InMemoryPipelineRepository(self._pipeline_store)
        self.contracts = InMemoryDataContractRepository(self._contract_store)
        self.ingestion_sources = InMemoryIngestionSourceRepository(self._source_store)
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
def connector_runtime() -> FakeConnectorRuntime:
    return FakeConnectorRuntime()


@pytest.fixture
def cache() -> FakeCache:
    return FakeCache()


@pytest.fixture
def components(
    store: dict[uuid.UUID, Pipeline],
    contract_store: dict[uuid.UUID, DataContract],
    source_store: dict[uuid.UUID, IngestionSource],
    connector_runtime: FakeConnectorRuntime,
    cache: FakeCache,
) -> AppComponents:
    async def _ok() -> bool:
        return True

    return AppComponents(
        uow_factory=lambda: InMemoryUnitOfWork(store, contract_store, source_store),
        cache=cache,
        token_verifier=StaticTokenVerifier(),
        schema_registry=FakeSchemaRegistry(),
        connector_runtime=connector_runtime,
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
            scopes=frozenset({"pipelines:read", "contracts:read", "ingestion:read"}),
        )


@pytest.fixture
def readonly_components(
    store: dict[uuid.UUID, Pipeline],
    contract_store: dict[uuid.UUID, DataContract],
    source_store: dict[uuid.UUID, IngestionSource],
    connector_runtime: FakeConnectorRuntime,
    cache: FakeCache,
) -> AppComponents:
    async def _ok() -> bool:
        return True

    return AppComponents(
        uow_factory=lambda: InMemoryUnitOfWork(store, contract_store, source_store),
        cache=cache,
        token_verifier=ReadOnlyTokenVerifier(),
        schema_registry=FakeSchemaRegistry(),
        connector_runtime=connector_runtime,
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
