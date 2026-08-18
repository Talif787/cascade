from __future__ import annotations

import structlog

from cascade.application.common.dto import Page
from cascade.application.common.errors import (
    ConflictError,
    InputValidationError,
    NotFoundError,
)
from cascade.application.common.unit_of_work import UnitOfWork, UnitOfWorkFactory
from cascade.application.copilot.commands import (
    AskCommand,
    GetCopilotQueryQuery,
    ListCopilotQueriesQuery,
)
from cascade.application.copilot.dto import CopilotAnswerView, CopilotQueryView
from cascade.application.copilot.translator import (
    Nl2SqlTranslator,
    TranslationColumn,
    TranslationError,
    TranslationResult,
    TranslationSchema,
)
from cascade.application.serving.runtime import ClickHouseRuntime, CompiledQuery
from cascade.domain.common.errors import DomainError, ValidationError
from cascade.domain.copilot.aggregate import CopilotQuery
from cascade.domain.copilot.repository import (
    CopilotQueryFilter,
    CopilotQuerySortField,
)
from cascade.domain.copilot.value_objects import (
    CopilotStatus,
    Question,
    TranslatedFilter,
    TranslatedMeasure,
    TranslatedQuery,
)
from cascade.domain.serving.aggregate import ServingView
from cascade.domain.serving.value_objects import (
    Aggregation,
    FilterClause,
    FilterOp,
    MeasureSelection,
    QueryRequest,
    ServingViewId,
    ServingViewName,
)

_logger = structlog.get_logger(__name__)

_MAX_PAGE_SIZE = 100


class CopilotApplicationService:
    """Turns questions into governed queries by validating against the serving schema."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        translator: Nl2SqlTranslator,
        runtime: ClickHouseRuntime,
    ) -> None:
        self._uow_factory = uow_factory
        self._translator = translator
        self._runtime = runtime

    async def ask(self, command: AskCommand) -> CopilotAnswerView:
        question = _build_question(command.question)
        async with self._uow_factory() as uow:
            view = await self._resolve_view(uow, command)
            query = CopilotQuery.ask(
                question=question, view_id=str(view.id), view_name=str(view.name)
            )

            schema = _schema_for(view)
            try:
                result = await self._translator.translate(str(question), schema)
            except TranslationError as exc:
                query.reject(f"translation failed: {exc}")
                await self._persist(uow, query)
                return _answer(query)

            translated = _to_translated_query(result)
            if translated is None:
                query.reject("the question could not be mapped to any known column")
                await self._persist(uow, query)
                return _answer(query)

            request = _to_query_request(translated)
            try:
                view.plan_query(request)
            except DomainError as exc:
                query.reject(f"rejected by serving policy: {exc}")
                await self._persist(uow, query)
                return _answer(query)

            query.record_translation(translated)

            if not command.execute:
                await self._persist(uow, query)
                return _answer(query)

            compiled = _compile(view, request)
            try:
                query_result = await self._runtime.query(compiled)
            except Exception as exc:
                query.fail(f"execution failed: {exc}")
                await self._persist(uow, query)
                raise ConflictError(f"query execution failed: {exc}") from exc

            rows = [dict(row) for row in query_result.rows]
            query.record_execution(len(rows))
            await self._persist(uow, query)
            return _answer(query, columns=list(query_result.columns), rows=rows)

    async def get_query(self, query: GetCopilotQueryQuery) -> CopilotQueryView:
        from cascade.domain.copilot.value_objects import CopilotQueryId

        identity = CopilotQueryId.from_string(query.query_id)
        async with self._uow_factory() as uow:
            found = await uow.copilot_queries.get(identity)
            if found is None:
                raise NotFoundError("copilot query", query.query_id)
            return CopilotQueryView.from_aggregate(found)

    async def list_queries(self, query: ListCopilotQueriesQuery) -> Page[CopilotQueryView]:
        size = _bounded_size(query.size)
        page = max(query.page, 1)
        repo_filter = CopilotQueryFilter(
            status=_parse_status(query.status),
            view_id=query.view_id,
            offset=(page - 1) * size,
            limit=size,
            sort_by=CopilotQuerySortField.CREATED_AT,
            descending=query.descending,
        )
        async with self._uow_factory() as uow:
            items, total = await uow.copilot_queries.list(repo_filter)
            return Page(
                items=[CopilotQueryView.from_aggregate(q) for q in items],
                total=total,
                page=page,
                size=size,
            )

    async def _resolve_view(self, uow: UnitOfWork, command: AskCommand) -> ServingView:
        if command.view_id:
            view = await uow.serving_views.get(ServingViewId.from_string(command.view_id))
            if view is None:
                raise NotFoundError("serving view", command.view_id)
            return view
        if command.view_name:
            try:
                name = ServingViewName(command.view_name)
            except ValidationError as exc:
                raise InputValidationError(str(exc)) from exc
            view = await uow.serving_views.get_by_name(name)
            if view is None:
                raise NotFoundError("serving view", command.view_name)
            return view
        raise InputValidationError("either view_id or view_name is required")

    async def _persist(self, uow: UnitOfWork, query: CopilotQuery) -> None:
        await uow.copilot_queries.add(query)
        await uow.commit()
        _emit_events(query)


def _schema_for(view: ServingView) -> TranslationSchema:
    return TranslationSchema(
        view_name=str(view.name),
        columns=tuple(
            TranslationColumn(name=c.name, role=c.role.value, type=c.type.value)
            for c in view.schema.columns
        ),
    )


def _to_translated_query(result: TranslationResult) -> TranslatedQuery | None:
    if not result.dimensions and not result.measures:
        return None
    try:
        return TranslatedQuery(
            dimensions=tuple(result.dimensions),
            measures=tuple(
                TranslatedMeasure(column=m.column, aggregation=m.aggregation)
                for m in result.measures
            ),
            filters=tuple(
                TranslatedFilter(column=f.column, op=f.op, values=tuple(f.values))
                for f in result.filters
            ),
            limit=result.limit,
        )
    except ValidationError:
        return None


def _to_query_request(translated: TranslatedQuery) -> QueryRequest:
    return QueryRequest(
        dimensions=tuple(translated.dimensions),
        measures=tuple(
            MeasureSelection(column=m.column, aggregation=_parse_aggregation(m.aggregation))
            for m in translated.measures
        ),
        filters=tuple(
            FilterClause(column=f.column, op=_parse_filter_op(f.op), values=tuple(f.values))
            for f in translated.filters
        ),
        limit=translated.limit,
    )


def _compile(view: ServingView, request: QueryRequest) -> CompiledQuery:
    plan = view.plan_query(request)
    return CompiledQuery(
        table=plan.table,
        dimensions=plan.dimensions,
        measures=plan.measures,
        filters=plan.filters,
        limit=plan.limit,
    )


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


def _build_question(raw: str) -> Question:
    try:
        return Question(raw)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _parse_status(raw: str | None) -> CopilotStatus | None:
    if raw is None:
        return None
    try:
        return CopilotStatus(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown copilot status {raw!r}") from exc


def _bounded_size(size: int) -> int:
    if size < 1:
        return 1
    return min(size, _MAX_PAGE_SIZE)


def _answer(
    query: CopilotQuery,
    columns: list[str] | None = None,
    rows: list[dict[str, object]] | None = None,
) -> CopilotAnswerView:
    return CopilotAnswerView.from_aggregate(query, columns or [], rows or [])


def _emit_events(query: CopilotQuery) -> None:
    for event in query.pull_events():
        _logger.info(
            "domain_event",
            event_type=event.event_type,
            query_id=str(query.id),
            occurred_at=event.occurred_at.isoformat(),
        )
