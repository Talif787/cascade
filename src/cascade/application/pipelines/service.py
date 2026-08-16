from __future__ import annotations

from collections.abc import Callable

import structlog

from cascade.application.common.dto import Page
from cascade.application.common.errors import (
    ConflictError,
    InputValidationError,
    NotFoundError,
)
from cascade.application.common.unit_of_work import UnitOfWork, UnitOfWorkFactory
from cascade.application.pipelines.commands import ConnectorInput, RegisterPipelineCommand
from cascade.application.pipelines.dto import PipelineView
from cascade.application.pipelines.queries import GetPipelineQuery, ListPipelinesQuery
from cascade.domain.common.errors import DomainError, ValidationError
from cascade.domain.pipelines.aggregate import Pipeline
from cascade.domain.pipelines.repository import (
    PipelineQuery,
    PipelineSortField,
)
from cascade.domain.pipelines.value_objects import (
    ConnectorType,
    PipelineId,
    PipelineName,
    PipelineStatus,
    SinkTarget,
    SinkType,
    SourceConnector,
)

_logger = structlog.get_logger(__name__)

_MAX_PAGE_SIZE = 100


class PipelineApplicationService:
    """Coordinates pipeline use cases across a unit of work."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def register_pipeline(self, command: RegisterPipelineCommand) -> PipelineView:
        name = _build_name(command.name)
        source = _build_source(command.source)
        sink = _build_sink(command.sink)

        async with self._uow_factory() as uow:
            if await uow.pipelines.exists_by_name(name):
                raise ConflictError(f"pipeline name {name!s} is already in use")
            pipeline = Pipeline.register(
                name=name, source=source, sink=sink, description=command.description
            )
            await uow.pipelines.add(pipeline)
            await uow.commit()
            _emit_events(pipeline)
            return PipelineView.from_aggregate(pipeline)

    async def activate_pipeline(self, pipeline_id: str) -> PipelineView:
        return await self._mutate(pipeline_id, lambda pipeline: pipeline.activate())

    async def pause_pipeline(self, pipeline_id: str) -> PipelineView:
        return await self._mutate(pipeline_id, lambda pipeline: pipeline.pause())

    async def archive_pipeline(self, pipeline_id: str) -> PipelineView:
        return await self._mutate(pipeline_id, lambda pipeline: pipeline.archive())

    async def get_pipeline(self, query: GetPipelineQuery) -> PipelineView:
        identity = PipelineId.from_string(query.pipeline_id)
        async with self._uow_factory() as uow:
            pipeline = await uow.pipelines.get(identity)
            if pipeline is None:
                raise NotFoundError("pipeline", query.pipeline_id)
            return PipelineView.from_aggregate(pipeline)

    async def list_pipelines(self, query: ListPipelinesQuery) -> Page[PipelineView]:
        size = _bounded_size(query.size)
        page = max(query.page, 1)
        repo_query = PipelineQuery(
            status=_parse_status(query.status),
            offset=(page - 1) * size,
            limit=size,
            sort_by=_parse_sort_field(query.sort_by),
            descending=query.descending,
        )
        async with self._uow_factory() as uow:
            pipelines, total = await uow.pipelines.list(repo_query)
            return Page(
                items=[PipelineView.from_aggregate(p) for p in pipelines],
                total=total,
                page=page,
                size=size,
            )

    async def _mutate(
        self, pipeline_id: str, operation: Callable[[Pipeline], None]
    ) -> PipelineView:
        identity = PipelineId.from_string(pipeline_id)
        async with self._uow_factory() as uow:
            pipeline = await self._load(uow, identity, pipeline_id)
            try:
                operation(pipeline)
            except DomainError as exc:
                raise ConflictError(str(exc)) from exc
            await uow.pipelines.update(pipeline)
            await uow.commit()
            _emit_events(pipeline)
            return PipelineView.from_aggregate(pipeline)

    async def _load(self, uow: UnitOfWork, identity: PipelineId, raw_id: str) -> Pipeline:
        pipeline = await uow.pipelines.get(identity)
        if pipeline is None:
            raise NotFoundError("pipeline", raw_id)
        return pipeline


def _build_name(raw: str) -> PipelineName:
    try:
        return PipelineName(raw)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_source(payload: ConnectorInput) -> SourceConnector:
    try:
        return SourceConnector(
            type=ConnectorType(payload.type), resource=payload.resource, options=payload.options
        )
    except ValueError as exc:
        raise InputValidationError(f"unsupported source connector type {payload.type!r}") from exc
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_sink(payload: ConnectorInput) -> SinkTarget:
    try:
        return SinkTarget(
            type=SinkType(payload.type), resource=payload.resource, options=payload.options
        )
    except ValueError as exc:
        raise InputValidationError(f"unsupported sink target type {payload.type!r}") from exc
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _parse_status(raw: str | None) -> PipelineStatus | None:
    if raw is None:
        return None
    try:
        return PipelineStatus(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown pipeline status {raw!r}") from exc


def _parse_sort_field(raw: str) -> PipelineSortField:
    try:
        return PipelineSortField(raw)
    except ValueError as exc:
        raise InputValidationError(f"cannot sort by {raw!r}") from exc


def _bounded_size(size: int) -> int:
    if size < 1:
        return 1
    return min(size, _MAX_PAGE_SIZE)


def _emit_events(pipeline: Pipeline) -> None:
    for event in pipeline.pull_events():
        _logger.info(
            "domain_event",
            event_type=event.event_type,
            pipeline_id=str(pipeline.id),
            occurred_at=event.occurred_at.isoformat(),
        )
