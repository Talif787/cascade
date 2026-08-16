from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.application.common.unit_of_work import UnitOfWork
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
    def __init__(self, store: dict[uuid.UUID, Pipeline]) -> None:
        self._store = store

    async def __aenter__(self) -> InMemoryUnitOfWork:
        self.pipelines = InMemoryPipelineRepository(self._store)
        return self

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


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
            scopes=frozenset({"pipelines:read", "pipelines:write"}),
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
def cache() -> FakeCache:
    return FakeCache()


@pytest.fixture
def components(store: dict[uuid.UUID, Pipeline], cache: FakeCache) -> AppComponents:
    async def _ok() -> bool:
        return True

    return AppComponents(
        uow_factory=lambda: InMemoryUnitOfWork(store),
        cache=cache,
        token_verifier=StaticTokenVerifier(),
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
