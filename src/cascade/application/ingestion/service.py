from __future__ import annotations

import structlog

from cascade.application.common.dto import Page
from cascade.application.common.errors import (
    ConflictError,
    InputValidationError,
    NotFoundError,
)
from cascade.application.common.unit_of_work import UnitOfWork, UnitOfWorkFactory
from cascade.application.ingestion.commands import (
    ChangeDeadLetterPolicyCommand,
    DeadLetterInput,
    RecordDeadLettersCommand,
    RegisterSourceCommand,
)
from cascade.application.ingestion.dto import SourceView
from cascade.application.ingestion.queries import (
    GetSourceQuery,
    ListSourcesQuery,
)
from cascade.application.ingestion.runtime import (
    ConnectorRuntime,
    ConnectorRuntimeError,
    ConnectorSpec,
)
from cascade.domain.common.errors import DomainError, ValidationError
from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.ingestion.aggregate import IngestionSource
from cascade.domain.ingestion.repository import (
    IngestionSourceQuery,
    SourceSortField,
)
from cascade.domain.ingestion.value_objects import (
    ConnectorConfig,
    ConnectorKind,
    DeadLetterPolicy,
    FailureAction,
    IngestionSourceId,
    SourceName,
    SourceStatus,
)
from cascade.domain.pipelines.value_objects import PipelineId

_logger = structlog.get_logger(__name__)

_MAX_PAGE_SIZE = 100


class IngestionApplicationService:
    """Coordinates ingestion source use cases and connector runtime side effects."""

    def __init__(self, uow_factory: UnitOfWorkFactory, runtime: ConnectorRuntime) -> None:
        self._uow_factory = uow_factory
        self._runtime = runtime

    async def register_source(self, command: RegisterSourceCommand) -> SourceView:
        name = _build_name(command.name)
        kind = _parse_kind(command.connector_kind)
        config = _build_config(command.config)
        policy = _build_policy(command.dead_letter)
        contract_id = DataContractId.from_string(command.contract_id)
        pipeline_id = PipelineId.from_string(command.pipeline_id) if command.pipeline_id else None

        async with self._uow_factory() as uow:
            if await uow.contracts.get(contract_id) is None:
                raise InputValidationError(f"contract {command.contract_id} does not exist")
            if pipeline_id is not None and await uow.pipelines.get(pipeline_id) is None:
                raise InputValidationError(f"pipeline {command.pipeline_id} does not exist")
            if await uow.ingestion_sources.exists_by_name(name):
                raise ConflictError(f"source name {name!s} is already in use")

            source = IngestionSource.register(
                name=name,
                connector_kind=kind,
                config=config,
                contract_id=contract_id,
                dead_letter_policy=policy,
                pipeline_id=pipeline_id,
                description=command.description,
            )
            await uow.ingestion_sources.add(source)
            await uow.commit()
            _emit_events(source)
            return SourceView.from_aggregate(source)

    async def provision_source(self, source_id: str) -> SourceView:
        identity = IngestionSourceId.from_string(source_id)
        async with self._uow_factory() as uow:
            source = await self._load(uow, identity, source_id)
            _apply_transition(source.begin_provisioning)
            spec = ConnectorSpec(
                name=_runtime_name(source),
                kind=source.connector_kind,
                config=source.config,
                dead_letter_policy=source.dead_letter_policy,
            )
            try:
                handle = await self._runtime.deploy(spec)
            except ConnectorRuntimeError as exc:
                source.mark_failed()
                await uow.ingestion_sources.update(source)
                await uow.commit()
                _emit_events(source)
                raise ConflictError(f"connector runtime rejected the source: {exc}") from exc
            source.mark_running(handle.name)
            await uow.ingestion_sources.update(source)
            await uow.commit()
            _emit_events(source)
            return SourceView.from_aggregate(source)

    async def pause_source(self, source_id: str) -> SourceView:
        return await self._runtime_transition(source_id, "pause")

    async def resume_source(self, source_id: str) -> SourceView:
        return await self._runtime_transition(source_id, "resume")

    async def decommission_source(self, source_id: str) -> SourceView:
        identity = IngestionSourceId.from_string(source_id)
        async with self._uow_factory() as uow:
            source = await self._load(uow, identity, source_id)
            ref = source.runtime_ref
            _apply_transition(source.decommission)
            if ref is not None:
                try:
                    await self._runtime.delete(ref)
                except ConnectorRuntimeError:
                    _logger.warning("connector_delete_failed", runtime_ref=ref)
            await uow.ingestion_sources.update(source)
            await uow.commit()
            _emit_events(source)
            return SourceView.from_aggregate(source)

    async def record_dead_letters(self, command: RecordDeadLettersCommand) -> SourceView:
        if command.count < 0:
            raise InputValidationError("dead-letter count must not be negative")
        identity = IngestionSourceId.from_string(command.source_id)
        async with self._uow_factory() as uow:
            source = await self._load(uow, identity, command.source_id)
            source.record_dead_letters(command.count)
            if source.status is SourceStatus.FAILED and source.runtime_ref is not None:
                try:
                    await self._runtime.pause(source.runtime_ref)
                except ConnectorRuntimeError:
                    _logger.warning("connector_pause_failed", runtime_ref=source.runtime_ref)
            await uow.ingestion_sources.update(source)
            await uow.commit()
            _emit_events(source)
            return SourceView.from_aggregate(source)

    async def change_dead_letter_policy(self, command: ChangeDeadLetterPolicyCommand) -> SourceView:
        policy = _build_policy(command.dead_letter)
        identity = IngestionSourceId.from_string(command.source_id)
        async with self._uow_factory() as uow:
            source = await self._load(uow, identity, command.source_id)
            source.change_dead_letter_policy(policy)
            await uow.ingestion_sources.update(source)
            await uow.commit()
            _emit_events(source)
            return SourceView.from_aggregate(source)

    async def get_source(self, query: GetSourceQuery) -> SourceView:
        identity = IngestionSourceId.from_string(query.source_id)
        async with self._uow_factory() as uow:
            source = await self._load(uow, identity, query.source_id)
            return SourceView.from_aggregate(source)

    async def list_sources(self, query: ListSourcesQuery) -> Page[SourceView]:
        size = _bounded_size(query.size)
        page = max(query.page, 1)
        repo_query = IngestionSourceQuery(
            status=_parse_status(query.status),
            connector_kind=_parse_optional_kind(query.connector_kind),
            contract_id=(
                DataContractId.from_string(query.contract_id) if query.contract_id else None
            ),
            offset=(page - 1) * size,
            limit=size,
            sort_by=_parse_sort_field(query.sort_by),
            descending=query.descending,
        )
        async with self._uow_factory() as uow:
            sources, total = await uow.ingestion_sources.list(repo_query)
            return Page(
                items=[SourceView.from_aggregate(s) for s in sources],
                total=total,
                page=page,
                size=size,
            )

    async def _runtime_transition(self, source_id: str, action: str) -> SourceView:
        identity = IngestionSourceId.from_string(source_id)
        async with self._uow_factory() as uow:
            source = await self._load(uow, identity, source_id)
            if action == "pause":
                _apply_transition(source.pause)
            else:
                _apply_transition(source.resume)
            if source.runtime_ref is not None:
                try:
                    if action == "pause":
                        await self._runtime.pause(source.runtime_ref)
                    else:
                        await self._runtime.resume(source.runtime_ref)
                except ConnectorRuntimeError as exc:
                    raise ConflictError(
                        f"connector runtime could not {action} the source: {exc}"
                    ) from exc
            await uow.ingestion_sources.update(source)
            await uow.commit()
            _emit_events(source)
            return SourceView.from_aggregate(source)

    async def _load(
        self, uow: UnitOfWork, identity: IngestionSourceId, raw_id: str
    ) -> IngestionSource:
        source = await uow.ingestion_sources.get(identity)
        if source is None:
            raise NotFoundError("ingestion source", raw_id)
        return source


def _runtime_name(source: IngestionSource) -> str:
    return f"cascade.{source.connector_kind.value}.{source.name!s}"


def _apply_transition(action: object) -> None:
    try:
        action()  # type: ignore[operator]
    except DomainError as exc:
        raise ConflictError(str(exc)) from exc


def _build_name(raw: str) -> SourceName:
    try:
        return SourceName(raw)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_config(raw: dict[str, str]) -> ConnectorConfig:
    try:
        return ConnectorConfig(options=dict(raw))
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_policy(payload: DeadLetterInput) -> DeadLetterPolicy:
    try:
        action = FailureAction(payload.on_failure)
    except ValueError as exc:
        raise InputValidationError(f"unknown failure action {payload.on_failure!r}") from exc
    try:
        return DeadLetterPolicy(
            on_failure=action,
            dlq_topic=payload.dlq_topic,
            max_retries=payload.max_retries,
            tolerance=payload.tolerance,
        )
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _parse_kind(raw: str) -> ConnectorKind:
    try:
        return ConnectorKind(raw)
    except ValueError as exc:
        raise InputValidationError(f"unsupported connector kind {raw!r}") from exc


def _parse_optional_kind(raw: str | None) -> ConnectorKind | None:
    return _parse_kind(raw) if raw else None


def _parse_status(raw: str | None) -> SourceStatus | None:
    if raw is None:
        return None
    try:
        return SourceStatus(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown source status {raw!r}") from exc


def _parse_sort_field(raw: str) -> SourceSortField:
    try:
        return SourceSortField(raw)
    except ValueError as exc:
        raise InputValidationError(f"cannot sort by {raw!r}") from exc


def _bounded_size(size: int) -> int:
    if size < 1:
        return 1
    return min(size, _MAX_PAGE_SIZE)


def _emit_events(source: IngestionSource) -> None:
    for event in source.pull_events():
        _logger.info(
            "domain_event",
            event_type=event.event_type,
            source_id=str(source.id),
            occurred_at=event.occurred_at.isoformat(),
        )
