from __future__ import annotations

import structlog

from cascade.application.common.dto import Page
from cascade.application.common.errors import (
    ConflictError,
    InputValidationError,
    NotFoundError,
)
from cascade.application.common.unit_of_work import UnitOfWork, UnitOfWorkFactory
from cascade.application.serving.commands import (
    ChangeRefreshScheduleCommand,
    ColumnInput,
    RegisterServingViewCommand,
    RunQueryCommand,
)
from cascade.application.serving.dto import (
    CatalogEntryView,
    QueryResultView,
    ServingViewView,
)
from cascade.application.serving.queries import (
    GetServingViewQuery,
    ListServingViewsQuery,
)
from cascade.application.serving.runtime import (
    ClickHouseRuntime,
    ClickHouseRuntimeError,
    CompiledQuery,
    ServingTableSpec,
)
from cascade.domain.common.errors import DomainError, ValidationError
from cascade.domain.lakehouse.value_objects import DatasetId
from cascade.domain.serving.aggregate import ServingView
from cascade.domain.serving.repository import (
    ServingViewQuery,
    ServingViewSortField,
)
from cascade.domain.serving.value_objects import (
    Aggregation,
    ClickHouseEngine,
    Column,
    ColumnRole,
    ColumnType,
    ExposedSchema,
    FilterClause,
    FilterOp,
    MeasureSelection,
    QueryRequest,
    RefreshMode,
    ServingStatus,
    ServingViewId,
    ServingViewName,
)

_logger = structlog.get_logger(__name__)

_MAX_PAGE_SIZE = 100


class ServingApplicationService:
    """Coordinates serving view use cases and ClickHouse runtime side effects."""

    def __init__(self, uow_factory: UnitOfWorkFactory, runtime: ClickHouseRuntime) -> None:
        self._uow_factory = uow_factory
        self._runtime = runtime

    async def register_serving_view(self, command: RegisterServingViewCommand) -> ServingViewView:
        name = _build_name(command.name)
        engine = _parse_engine(command.engine)
        refresh_mode = _parse_refresh_mode(command.refresh_mode)
        schema = _build_schema(command)
        source_id = DatasetId.from_string(command.source_dataset_id)

        async with self._uow_factory() as uow:
            source = await uow.datasets.get(source_id)
            if source is None:
                raise InputValidationError(
                    f"source dataset {command.source_dataset_id} does not exist"
                )
            if await uow.serving_views.exists_by_name(name):
                raise ConflictError(f"serving view name {name!s} is already in use")

            try:
                view = ServingView.register(
                    name=name,
                    source_dataset_id=source_id,
                    engine=engine,
                    schema=schema,
                    refresh_mode=refresh_mode,
                    refresh_cron=command.refresh_cron,
                    refresh_enabled=command.refresh_enabled,
                    description=command.description,
                )
            except ValidationError as exc:
                raise InputValidationError(str(exc)) from exc

            spec = _table_spec(view, str(source.name))
            try:
                await self._runtime.create_or_replace(spec)
            except ClickHouseRuntimeError as exc:
                raise ConflictError(f"clickhouse rejected the table: {exc}") from exc

            await uow.serving_views.add(view)
            await uow.commit()
            _emit_events(view)
            return ServingViewView.from_aggregate(view)

    async def sync_serving_view(self, view_id: str) -> ServingViewView:
        identity = ServingViewId.from_string(view_id)
        async with self._uow_factory() as uow:
            view = await self._load(uow, identity, view_id)
            source = await uow.datasets.get(view.source_dataset_id)
            source_at = source.last_materialized_at if source is not None else None
            spec = _table_spec(view, str(source.name) if source is not None else "")
            _apply_transition(lambda: view.begin_sync(_pending_ref(view)))
            try:
                result = await self._runtime.sync(spec)
            except ClickHouseRuntimeError as exc:
                view.fail_sync(str(exc))
                await uow.serving_views.update(view)
                await uow.commit()
                _emit_events(view)
                raise ConflictError(f"clickhouse sync failed: {exc}") from exc
            view.complete_sync(result.sync_ref, result.row_count, source_at)
            await uow.serving_views.update(view)
            await uow.commit()
            _emit_events(view)
            return ServingViewView.from_aggregate(view)

    async def reconcile_serving_view(self, view_id: str) -> ServingViewView:
        identity = ServingViewId.from_string(view_id)
        async with self._uow_factory() as uow:
            view = await self._load(uow, identity, view_id)
            source = await uow.datasets.get(view.source_dataset_id)
            source_at = source.last_materialized_at if source is not None else None
            if view.reconcile(source_at):
                await uow.serving_views.update(view)
                await uow.commit()
                _emit_events(view)
            return ServingViewView.from_aggregate(view)

    async def change_schedule(self, command: ChangeRefreshScheduleCommand) -> ServingViewView:
        identity = ServingViewId.from_string(command.view_id)
        async with self._uow_factory() as uow:
            view = await self._load(uow, identity, command.view_id)
            view.change_schedule(command.refresh_cron, command.refresh_enabled)
            await uow.serving_views.update(view)
            await uow.commit()
            _emit_events(view)
            return ServingViewView.from_aggregate(view)

    async def retire_serving_view(self, view_id: str) -> ServingViewView:
        identity = ServingViewId.from_string(view_id)
        async with self._uow_factory() as uow:
            view = await self._load(uow, identity, view_id)
            _apply_transition(view.retire)
            try:
                await self._runtime.drop(str(view.name))
            except ClickHouseRuntimeError:
                _logger.warning("clickhouse_drop_failed", view=str(view.name))
            await uow.serving_views.update(view)
            await uow.commit()
            _emit_events(view)
            return ServingViewView.from_aggregate(view)

    async def run_query(self, command: RunQueryCommand) -> QueryResultView:
        identity = ServingViewId.from_string(command.view_id)
        request = _build_query_request(command)
        async with self._uow_factory() as uow:
            view = await self._load(uow, identity, command.view_id)
            try:
                plan = view.plan_query(request)
            except DomainError as exc:
                raise _query_error(exc) from exc
        compiled = CompiledQuery(
            table=plan.table,
            dimensions=plan.dimensions,
            measures=plan.measures,
            filters=plan.filters,
            limit=plan.limit,
        )
        try:
            result = await self._runtime.query(compiled)
        except ClickHouseRuntimeError as exc:
            raise ConflictError(f"clickhouse query failed: {exc}") from exc
        rows = [dict(row) for row in result.rows]
        return QueryResultView(columns=list(result.columns), rows=rows, row_count=len(rows))

    async def get_serving_view(self, query: GetServingViewQuery) -> ServingViewView:
        identity = ServingViewId.from_string(query.view_id)
        async with self._uow_factory() as uow:
            view = await self._load(uow, identity, query.view_id)
            return ServingViewView.from_aggregate(view)

    async def get_catalog(self) -> list[CatalogEntryView]:
        async with self._uow_factory() as uow:
            views = await uow.serving_views.list_ready()
            return [CatalogEntryView.from_aggregate(view) for view in views]

    async def list_serving_views(self, query: ListServingViewsQuery) -> Page[ServingViewView]:
        size = _bounded_size(query.size)
        page = max(query.page, 1)
        repo_query = ServingViewQuery(
            status=_parse_status(query.status),
            engine=_parse_optional_engine(query.engine),
            source_dataset_id=(
                DatasetId.from_string(query.source_dataset_id) if query.source_dataset_id else None
            ),
            offset=(page - 1) * size,
            limit=size,
            sort_by=_parse_sort_field(query.sort_by),
            descending=query.descending,
        )
        async with self._uow_factory() as uow:
            views, total = await uow.serving_views.list(repo_query)
            return Page(
                items=[ServingViewView.from_aggregate(v) for v in views],
                total=total,
                page=page,
                size=size,
            )

    async def _load(self, uow: UnitOfWork, identity: ServingViewId, raw_id: str) -> ServingView:
        view = await uow.serving_views.get(identity)
        if view is None:
            raise NotFoundError("serving view", raw_id)
        return view


def _table_spec(view: ServingView, source_table: str) -> ServingTableSpec:
    return ServingTableSpec(
        name=str(view.name),
        engine=view.engine,
        columns=view.schema.columns,
        order_by=view.schema.order_by,
        partition_by=view.schema.partition_by,
        source_table=source_table,
    )


def _pending_ref(view: ServingView) -> str:
    return f"pending.{str(view.name).replace('.', '_')}"


def _apply_transition(action: object) -> None:
    try:
        action()  # type: ignore[operator]
    except DomainError as exc:
        raise ConflictError(str(exc)) from exc


def _query_error(exc: DomainError) -> Exception:
    from cascade.domain.serving.errors import InvalidQuery, ViewNotQueryable

    if isinstance(exc, InvalidQuery):
        return InputValidationError(str(exc))
    if isinstance(exc, ViewNotQueryable):
        return ConflictError(str(exc))
    return ConflictError(str(exc))


def _build_name(raw: str) -> ServingViewName:
    try:
        return ServingViewName(raw)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_schema(command: RegisterServingViewCommand) -> ExposedSchema:
    try:
        columns = tuple(_build_column(c) for c in command.columns)
        return ExposedSchema(
            columns=columns,
            order_by=tuple(command.order_by),
            partition_by=command.partition_by,
        )
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_column(payload: ColumnInput) -> Column:
    try:
        column_type = ColumnType(payload.type)
    except ValueError as exc:
        raise InputValidationError(f"unknown column type {payload.type!r}") from exc
    try:
        role = ColumnRole(payload.role)
    except ValueError as exc:
        raise InputValidationError(f"unknown column role {payload.role!r}") from exc
    return Column(name=payload.name, type=column_type, role=role, nullable=payload.nullable)


def _build_query_request(command: RunQueryCommand) -> QueryRequest:
    measures = tuple(
        MeasureSelection(column=m.column, aggregation=_parse_aggregation(m.aggregation))
        for m in command.measures
    )
    filters = tuple(
        FilterClause(column=f.column, op=_parse_filter_op(f.op), values=tuple(f.values))
        for f in command.filters
    )
    return QueryRequest(
        dimensions=tuple(command.dimensions),
        measures=measures,
        filters=filters,
        limit=command.limit,
    )


def _parse_engine(raw: str) -> ClickHouseEngine:
    try:
        return ClickHouseEngine(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown engine {raw!r}") from exc


def _parse_optional_engine(raw: str | None) -> ClickHouseEngine | None:
    return _parse_engine(raw) if raw else None


def _parse_refresh_mode(raw: str) -> RefreshMode:
    try:
        return RefreshMode(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown refresh mode {raw!r}") from exc


def _parse_aggregation(raw: str) -> Aggregation:
    try:
        return Aggregation(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown aggregation {raw!r}") from exc


def _parse_filter_op(raw: str) -> FilterOp:
    try:
        return FilterOp(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown filter operator {raw!r}") from exc


def _parse_status(raw: str | None) -> ServingStatus | None:
    if raw is None:
        return None
    try:
        return ServingStatus(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown serving status {raw!r}") from exc


def _parse_sort_field(raw: str) -> ServingViewSortField:
    try:
        return ServingViewSortField(raw)
    except ValueError as exc:
        raise InputValidationError(f"cannot sort by {raw!r}") from exc


def _bounded_size(size: int) -> int:
    if size < 1:
        return 1
    return min(size, _MAX_PAGE_SIZE)


def _emit_events(view: ServingView) -> None:
    for event in view.pull_events():
        _logger.info(
            "domain_event",
            event_type=event.event_type,
            view_id=str(view.id),
            occurred_at=event.occurred_at.isoformat(),
        )
