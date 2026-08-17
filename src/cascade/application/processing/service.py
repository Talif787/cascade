from __future__ import annotations

import structlog

from cascade.application.common.dto import Page
from cascade.application.common.errors import (
    ConflictError,
    InputValidationError,
    NotFoundError,
)
from cascade.application.common.unit_of_work import UnitOfWork, UnitOfWorkFactory
from cascade.application.processing.commands import (
    ChangeCheckpointConfigCommand,
    CheckpointInput,
    DefineJobCommand,
    EndpointInput,
    RestartInput,
)
from cascade.application.processing.dto import JobView
from cascade.application.processing.queries import GetJobQuery, ListJobsQuery
from cascade.application.processing.runtime import (
    FlinkRuntime,
    FlinkRuntimeError,
    JobSpec,
)
from cascade.domain.common.errors import DomainError, ValidationError
from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.processing.aggregate import StreamJob
from cascade.domain.processing.repository import JobSortField, StreamJobQuery
from cascade.domain.processing.value_objects import (
    CheckpointConfig,
    DeliveryGuarantee,
    JobName,
    JobSink,
    JobSource,
    JobStatus,
    RestartKind,
    RestartStrategy,
    SinkKind,
    SourceKind,
    StreamJobId,
)

_logger = structlog.get_logger(__name__)

_MAX_PAGE_SIZE = 100


class StreamProcessingApplicationService:
    """Coordinates stream-job use cases and Flink runtime side effects."""

    def __init__(self, uow_factory: UnitOfWorkFactory, runtime: FlinkRuntime) -> None:
        self._uow_factory = uow_factory
        self._runtime = runtime

    async def define_job(self, command: DefineJobCommand) -> JobView:
        name = _build_name(command.name)
        source = _build_source(command.source)
        sink = _build_sink(command.sink)
        guarantee = _parse_guarantee(command.delivery_guarantee)
        checkpoint = _build_checkpoint(command.checkpoint)
        restart = _build_restart(command.restart)
        contract_id = (
            DataContractId.from_string(command.contract_id) if command.contract_id else None
        )

        async with self._uow_factory() as uow:
            if contract_id is not None and await uow.contracts.get(contract_id) is None:
                raise InputValidationError(f"contract {command.contract_id} does not exist")
            if await uow.stream_jobs.exists_by_name(name):
                raise ConflictError(f"job name {name!s} is already in use")

            try:
                job = StreamJob.define(
                    name=name,
                    source=source,
                    sink=sink,
                    delivery_guarantee=guarantee,
                    checkpoint_config=checkpoint,
                    restart_strategy=restart,
                    parallelism=command.parallelism,
                    contract_id=contract_id,
                    description=command.description,
                )
            except ValidationError as exc:
                raise InputValidationError(str(exc)) from exc

            await uow.stream_jobs.add(job)
            await uow.commit()
            _emit_events(job)
            return JobView.from_aggregate(job)

    async def submit_job(self, job_id: str) -> JobView:
        identity = StreamJobId.from_string(job_id)
        async with self._uow_factory() as uow:
            job = await self._load(uow, identity, job_id)
            spec = _spec_from_job(job)
            try:
                handle = await self._runtime.submit(spec)
            except FlinkRuntimeError as exc:
                if job.status is JobStatus.DEFINED:
                    _apply_transition(job.cancel)
                await uow.stream_jobs.update(job)
                await uow.commit()
                _emit_events(job)
                raise ConflictError(f"flink runtime rejected the job: {exc}") from exc
            _apply_transition(lambda: job.submit(handle.job_id))
            _apply_transition(job.mark_running)
            await uow.stream_jobs.update(job)
            await uow.commit()
            _emit_events(job)
            return JobView.from_aggregate(job)

    async def suspend_job(self, job_id: str) -> JobView:
        identity = StreamJobId.from_string(job_id)
        async with self._uow_factory() as uow:
            job = await self._load(uow, identity, job_id)
            if job.runtime_ref is None:
                raise ConflictError("job has no runtime reference to suspend")
            try:
                location = await self._runtime.stop_with_savepoint(job.runtime_ref)
            except FlinkRuntimeError as exc:
                raise ConflictError(f"flink runtime could not suspend the job: {exc}") from exc
            _apply_transition(lambda: job.suspend(location))
            await uow.stream_jobs.update(job)
            await uow.commit()
            _emit_events(job)
            return JobView.from_aggregate(job)

    async def resume_job(self, job_id: str) -> JobView:
        identity = StreamJobId.from_string(job_id)
        async with self._uow_factory() as uow:
            job = await self._load(uow, identity, job_id)
            spec = _spec_from_job(job)
            try:
                handle = await self._runtime.submit(spec)
            except FlinkRuntimeError as exc:
                raise ConflictError(f"flink runtime could not resume the job: {exc}") from exc
            _apply_transition(job.resume)
            job._runtime_ref = handle.job_id
            await uow.stream_jobs.update(job)
            await uow.commit()
            _emit_events(job)
            return JobView.from_aggregate(job)

    async def cancel_job(self, job_id: str) -> JobView:
        identity = StreamJobId.from_string(job_id)
        async with self._uow_factory() as uow:
            job = await self._load(uow, identity, job_id)
            ref = job.runtime_ref
            _apply_transition(job.cancel)
            if ref is not None:
                try:
                    await self._runtime.cancel(ref)
                except FlinkRuntimeError:
                    _logger.warning("flink_cancel_failed", runtime_ref=ref)
            await uow.stream_jobs.update(job)
            await uow.commit()
            _emit_events(job)
            return JobView.from_aggregate(job)

    async def trigger_savepoint(self, job_id: str) -> JobView:
        identity = StreamJobId.from_string(job_id)
        async with self._uow_factory() as uow:
            job = await self._load(uow, identity, job_id)
            if job.runtime_ref is None:
                raise ConflictError("job has no runtime reference for a savepoint")
            try:
                location = await self._runtime.trigger_savepoint(job.runtime_ref)
            except FlinkRuntimeError as exc:
                raise ConflictError(f"flink runtime could not take a savepoint: {exc}") from exc
            _apply_transition(lambda: job.trigger_savepoint(location))
            await uow.stream_jobs.update(job)
            await uow.commit()
            _emit_events(job)
            return JobView.from_aggregate(job)

    async def change_checkpoint_config(self, command: ChangeCheckpointConfigCommand) -> JobView:
        checkpoint = _build_checkpoint(command.checkpoint)
        identity = StreamJobId.from_string(command.job_id)
        async with self._uow_factory() as uow:
            job = await self._load(uow, identity, command.job_id)
            try:
                job.change_checkpoint_config(checkpoint)
            except ValidationError as exc:
                raise InputValidationError(str(exc)) from exc
            await uow.stream_jobs.update(job)
            await uow.commit()
            _emit_events(job)
            return JobView.from_aggregate(job)

    async def get_job(self, query: GetJobQuery) -> JobView:
        identity = StreamJobId.from_string(query.job_id)
        async with self._uow_factory() as uow:
            job = await self._load(uow, identity, query.job_id)
            return JobView.from_aggregate(job)

    async def list_jobs(self, query: ListJobsQuery) -> Page[JobView]:
        size = _bounded_size(query.size)
        page = max(query.page, 1)
        repo_query = StreamJobQuery(
            status=_parse_status(query.status),
            sink_kind=_parse_sink_kind(query.sink_kind),
            delivery_guarantee=_parse_optional_guarantee(query.delivery_guarantee),
            contract_id=(
                DataContractId.from_string(query.contract_id) if query.contract_id else None
            ),
            offset=(page - 1) * size,
            limit=size,
            sort_by=_parse_sort_field(query.sort_by),
            descending=query.descending,
        )
        async with self._uow_factory() as uow:
            jobs, total = await uow.stream_jobs.list(repo_query)
            return Page(
                items=[JobView.from_aggregate(j) for j in jobs],
                total=total,
                page=page,
                size=size,
            )

    async def _load(self, uow: UnitOfWork, identity: StreamJobId, raw_id: str) -> StreamJob:
        job = await uow.stream_jobs.get(identity)
        if job is None:
            raise NotFoundError("stream job", raw_id)
        return job


def _spec_from_job(job: StreamJob) -> JobSpec:
    return JobSpec(
        name=str(job.name),
        source=job.source,
        sink=job.sink,
        delivery_guarantee=job.delivery_guarantee,
        checkpoint_config=job.checkpoint_config,
        restart_strategy=job.restart_strategy,
        parallelism=job.parallelism,
        savepoint_location=job.savepoint_location,
    )


def _apply_transition(action: object) -> None:
    try:
        action()  # type: ignore[operator]
    except DomainError as exc:
        raise ConflictError(str(exc)) from exc


def _build_name(raw: str) -> JobName:
    try:
        return JobName(raw)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_source(payload: EndpointInput) -> JobSource:
    try:
        return JobSource(kind=SourceKind(payload.kind), resource=payload.resource)
    except ValueError as exc:
        raise InputValidationError(f"unsupported source kind {payload.kind!r}") from exc
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_sink(payload: EndpointInput) -> JobSink:
    try:
        return JobSink(kind=SinkKind(payload.kind), resource=payload.resource)
    except ValueError as exc:
        raise InputValidationError(f"unsupported sink kind {payload.kind!r}") from exc
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_checkpoint(payload: CheckpointInput) -> CheckpointConfig:
    try:
        return CheckpointConfig(
            interval_ms=payload.interval_ms,
            timeout_ms=payload.timeout_ms,
            min_pause_ms=payload.min_pause_ms,
            max_concurrent=payload.max_concurrent,
        )
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_restart(payload: RestartInput) -> RestartStrategy:
    try:
        kind = RestartKind(payload.kind)
    except ValueError as exc:
        raise InputValidationError(f"unknown restart strategy {payload.kind!r}") from exc
    try:
        return RestartStrategy(kind=kind, attempts=payload.attempts, delay_ms=payload.delay_ms)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _parse_guarantee(raw: str) -> DeliveryGuarantee:
    try:
        return DeliveryGuarantee(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown delivery guarantee {raw!r}") from exc


def _parse_optional_guarantee(raw: str | None) -> DeliveryGuarantee | None:
    return _parse_guarantee(raw) if raw else None


def _parse_sink_kind(raw: str | None) -> SinkKind | None:
    if raw is None:
        return None
    try:
        return SinkKind(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown sink kind {raw!r}") from exc


def _parse_status(raw: str | None) -> JobStatus | None:
    if raw is None:
        return None
    try:
        return JobStatus(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown job status {raw!r}") from exc


def _parse_sort_field(raw: str) -> JobSortField:
    try:
        return JobSortField(raw)
    except ValueError as exc:
        raise InputValidationError(f"cannot sort by {raw!r}") from exc


def _bounded_size(size: int) -> int:
    if size < 1:
        return 1
    return min(size, _MAX_PAGE_SIZE)


def _emit_events(job: StreamJob) -> None:
    for event in job.pull_events():
        _logger.info(
            "domain_event",
            event_type=event.event_type,
            job_id=str(job.id),
            occurred_at=event.occurred_at.isoformat(),
        )
