from __future__ import annotations

import structlog

from cascade.application.common.dto import Page
from cascade.application.common.errors import (
    ConflictError,
    InputValidationError,
    NotFoundError,
)
from cascade.application.common.unit_of_work import UnitOfWork, UnitOfWorkFactory
from cascade.application.lakehouse.commands import (
    ChangeScheduleCommand,
    QualityCheckInput,
    RegisterDatasetCommand,
    ScheduleInput,
    TransformationInput,
)
from cascade.application.lakehouse.dto import (
    DatasetRefView,
    DatasetView,
    LineageView,
)
from cascade.application.lakehouse.orchestration import Orchestrator, OrchestratorError
from cascade.application.lakehouse.queries import (
    GetDatasetQuery,
    GetLineageQuery,
    ListDatasetsQuery,
)
from cascade.application.lakehouse.transformation import (
    TransformationRuntime,
    TransformationRuntimeError,
    TransformationSpec,
)
from cascade.domain.common.errors import DomainError, ValidationError
from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.lakehouse.aggregate import Dataset
from cascade.domain.lakehouse.repository import DatasetQuery, DatasetSortField
from cascade.domain.lakehouse.value_objects import (
    DatasetId,
    DatasetName,
    DatasetRef,
    DatasetStatus,
    Materialization,
    MedallionLayer,
    QualityCheck,
    QualityCheckKind,
    QualityOutcome,
    QualityStatus,
    Schedule,
    Transformation,
    TransformationEngine,
)

_logger = structlog.get_logger(__name__)

_MAX_PAGE_SIZE = 100


class LakehouseApplicationService:
    """Coordinates dataset use cases, dbt materialization, and Airflow scheduling."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        transformation_runtime: TransformationRuntime,
        orchestrator: Orchestrator,
    ) -> None:
        self._uow_factory = uow_factory
        self._runtime = transformation_runtime
        self._orchestrator = orchestrator

    async def register_dataset(self, command: RegisterDatasetCommand) -> DatasetView:
        name = _build_name(command.name)
        layer = _parse_layer(command.layer)
        transformation = _build_transformation(command.transformation)
        schedule = _build_schedule(command.schedule)
        quality_checks = tuple(_build_quality_check(q) for q in command.quality_checks)
        contract_id = (
            DataContractId.from_string(command.contract_id) if command.contract_id else None
        )

        async with self._uow_factory() as uow:
            if contract_id is not None and await uow.contracts.get(contract_id) is None:
                raise InputValidationError(f"contract {command.contract_id} does not exist")
            if await uow.datasets.exists_by_name(name):
                raise ConflictError(f"dataset name {name!s} is already in use")

            upstreams = await self._resolve_upstreams(uow, command.upstream_ids)
            try:
                dataset = Dataset.register(
                    name=name,
                    layer=layer,
                    transformation=transformation,
                    schedule=schedule,
                    upstreams=upstreams,
                    quality_checks=quality_checks,
                    contract_id=contract_id,
                    description=command.description,
                )
            except ValidationError as exc:
                raise InputValidationError(str(exc)) from exc

            await uow.datasets.add(dataset)
            if schedule.enabled:
                await self._safe_upsert_schedule(dataset)
            await uow.commit()
            _emit_events(dataset)
            return DatasetView.from_aggregate(dataset)

    async def materialize_dataset(self, dataset_id: str) -> DatasetView:
        identity = DatasetId.from_string(dataset_id)
        async with self._uow_factory() as uow:
            dataset = await self._load(uow, identity, dataset_id)
            spec = TransformationSpec(
                name=str(dataset.name),
                layer=dataset.layer,
                engine=dataset.transformation.engine,
                identifier=dataset.transformation.identifier,
                materialization=dataset.transformation.materialization,
                quality_checks=dataset.quality_checks,
            )
            _apply_transition(lambda: dataset.begin_materialization(_pending_ref(dataset)))
            try:
                result = await self._runtime.run(spec)
            except TransformationRuntimeError as exc:
                dataset.fail_materialization(str(exc))
                await uow.datasets.update(dataset)
                await uow.commit()
                _emit_events(dataset)
                raise ConflictError(f"transformation runtime failed: {exc}") from exc

            outcomes = tuple(
                QualityOutcome(name=o.name, passed=o.passed, detail=o.detail)
                for o in result.quality
            )
            dataset.complete_materialization(result.run_ref, result.row_count, outcomes)
            await uow.datasets.update(dataset)

            if dataset.status is DatasetStatus.MATERIALIZED:
                await self._mark_dependents_stale(uow, identity)

            await uow.commit()
            _emit_events(dataset)
            return DatasetView.from_aggregate(dataset)

    async def change_schedule(self, command: ChangeScheduleCommand) -> DatasetView:
        schedule = _build_schedule(command.schedule)
        identity = DatasetId.from_string(command.dataset_id)
        async with self._uow_factory() as uow:
            dataset = await self._load(uow, identity, command.dataset_id)
            dataset.change_schedule(schedule)
            await uow.datasets.update(dataset)
            if schedule.enabled:
                await self._safe_upsert_schedule(dataset)
            else:
                await self._safe_pause(dataset)
            await uow.commit()
            _emit_events(dataset)
            return DatasetView.from_aggregate(dataset)

    async def deprecate_dataset(self, dataset_id: str) -> DatasetView:
        identity = DatasetId.from_string(dataset_id)
        async with self._uow_factory() as uow:
            dataset = await self._load(uow, identity, dataset_id)
            _apply_transition(dataset.deprecate)
            await self._safe_pause(dataset)
            await uow.datasets.update(dataset)
            await uow.commit()
            _emit_events(dataset)
            return DatasetView.from_aggregate(dataset)

    async def get_dataset(self, query: GetDatasetQuery) -> DatasetView:
        identity = DatasetId.from_string(query.dataset_id)
        async with self._uow_factory() as uow:
            dataset = await self._load(uow, identity, query.dataset_id)
            return DatasetView.from_aggregate(dataset)

    async def get_lineage(self, query: GetLineageQuery) -> LineageView:
        identity = DatasetId.from_string(query.dataset_id)
        async with self._uow_factory() as uow:
            dataset = await self._load(uow, identity, query.dataset_id)
            dependents = await uow.datasets.list_dependents(identity)
            return LineageView(
                dataset=DatasetRefView(
                    id=str(dataset.id), name=str(dataset.name), layer=dataset.layer.value
                ),
                upstreams=[DatasetRefView.from_vo(ref) for ref in dataset.upstreams],
                downstreams=[
                    DatasetRefView(id=str(dep.id), name=str(dep.name), layer=dep.layer.value)
                    for dep in dependents
                ],
            )

    async def list_datasets(self, query: ListDatasetsQuery) -> Page[DatasetView]:
        size = _bounded_size(query.size)
        page = max(query.page, 1)
        repo_query = DatasetQuery(
            layer=_parse_optional_layer(query.layer),
            status=_parse_status(query.status),
            quality_status=_parse_quality_status(query.quality_status),
            contract_id=(
                DataContractId.from_string(query.contract_id) if query.contract_id else None
            ),
            offset=(page - 1) * size,
            limit=size,
            sort_by=_parse_sort_field(query.sort_by),
            descending=query.descending,
        )
        async with self._uow_factory() as uow:
            datasets, total = await uow.datasets.list(repo_query)
            return Page(
                items=[DatasetView.from_aggregate(d) for d in datasets],
                total=total,
                page=page,
                size=size,
            )

    async def _resolve_upstreams(
        self, uow: UnitOfWork, upstream_ids: tuple[str, ...]
    ) -> tuple[DatasetRef, ...]:
        refs: list[DatasetRef] = []
        for raw in upstream_ids:
            identity = DatasetId.from_string(raw)
            upstream = await uow.datasets.get(identity)
            if upstream is None:
                raise InputValidationError(f"upstream dataset {raw} does not exist")
            refs.append(
                DatasetRef(dataset_id=upstream.id, name=upstream.name, layer=upstream.layer)
            )
        return tuple(refs)

    async def _mark_dependents_stale(self, uow: UnitOfWork, dataset_id: DatasetId) -> None:
        for dependent in await uow.datasets.list_dependents(dataset_id):
            if dependent.status is DatasetStatus.MATERIALIZED:
                dependent.mark_stale()
                await uow.datasets.update(dependent)
                _emit_events(dependent)

    async def _safe_upsert_schedule(self, dataset: Dataset) -> None:
        try:
            await self._orchestrator.upsert_schedule(
                _dag_id(dataset),
                dataset.schedule.cron,
                dataset.schedule.timezone,
                dataset.schedule.enabled,
            )
        except OrchestratorError:
            _logger.warning("orchestrator_schedule_failed", dataset=str(dataset.name))

    async def _safe_pause(self, dataset: Dataset) -> None:
        try:
            await self._orchestrator.pause(_dag_id(dataset))
        except OrchestratorError:
            _logger.warning("orchestrator_pause_failed", dataset=str(dataset.name))

    async def _load(self, uow: UnitOfWork, identity: DatasetId, raw_id: str) -> Dataset:
        dataset = await uow.datasets.get(identity)
        if dataset is None:
            raise NotFoundError("dataset", raw_id)
        return dataset


def _dag_id(dataset: Dataset) -> str:
    return f"cascade.{str(dataset.name).replace('.', '_')}"


def _pending_ref(dataset: Dataset) -> str:
    return f"pending.{str(dataset.name).replace('.', '_')}"


def _apply_transition(action: object) -> None:
    try:
        action()  # type: ignore[operator]
    except DomainError as exc:
        raise ConflictError(str(exc)) from exc


def _build_name(raw: str) -> DatasetName:
    try:
        return DatasetName(raw)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_transformation(payload: TransformationInput) -> Transformation:
    try:
        engine = TransformationEngine(payload.engine)
    except ValueError as exc:
        raise InputValidationError(f"unknown transformation engine {payload.engine!r}") from exc
    try:
        materialization = Materialization(payload.materialization)
    except ValueError as exc:
        raise InputValidationError(f"unknown materialization {payload.materialization!r}") from exc
    try:
        return Transformation(
            engine=engine, identifier=payload.identifier, materialization=materialization
        )
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_schedule(payload: ScheduleInput) -> Schedule:
    try:
        return Schedule(cron=payload.cron, timezone=payload.timezone, enabled=payload.enabled)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_quality_check(payload: QualityCheckInput) -> QualityCheck:
    try:
        kind = QualityCheckKind(payload.kind)
    except ValueError as exc:
        raise InputValidationError(f"unknown quality check {payload.kind!r}") from exc
    try:
        return QualityCheck(
            kind=kind,
            column=payload.column,
            threshold=payload.threshold,
            accepted_values=tuple(payload.accepted_values),
        )
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _parse_layer(raw: str) -> MedallionLayer:
    try:
        return MedallionLayer(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown medallion layer {raw!r}") from exc


def _parse_optional_layer(raw: str | None) -> MedallionLayer | None:
    return _parse_layer(raw) if raw else None


def _parse_status(raw: str | None) -> DatasetStatus | None:
    if raw is None:
        return None
    try:
        return DatasetStatus(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown dataset status {raw!r}") from exc


def _parse_quality_status(raw: str | None) -> QualityStatus | None:
    if raw is None:
        return None
    try:
        return QualityStatus(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown quality status {raw!r}") from exc


def _parse_sort_field(raw: str) -> DatasetSortField:
    try:
        return DatasetSortField(raw)
    except ValueError as exc:
        raise InputValidationError(f"cannot sort by {raw!r}") from exc


def _bounded_size(size: int) -> int:
    if size < 1:
        return 1
    return min(size, _MAX_PAGE_SIZE)


def _emit_events(dataset: Dataset) -> None:
    for event in dataset.pull_events():
        _logger.info(
            "domain_event",
            event_type=event.event_type,
            dataset_id=str(dataset.id),
            occurred_at=event.occurred_at.isoformat(),
        )
