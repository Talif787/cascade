from __future__ import annotations

from datetime import UTC, datetime

import structlog

from cascade.application.common.dto import Page
from cascade.application.common.errors import (
    ConflictError,
    InputValidationError,
    NotFoundError,
)
from cascade.application.common.unit_of_work import UnitOfWork, UnitOfWorkFactory
from cascade.application.governance.commands import (
    ChangeFreshnessTargetCommand,
    ImportCostsCommand,
    RecordCostCommand,
    RegisterSloCommand,
)
from cascade.application.governance.cost_source import CostSource, CostSourceError
from cascade.application.governance.dto import (
    CostEntryView,
    CostReportView,
    ImportResultView,
    LineageEdgeView,
    LineageNodeView,
    LineageView,
    SloView,
)
from cascade.application.governance.queries import (
    CostReportQuery,
    GetLineageQuery,
    GetSloQuery,
    ListSlosQuery,
)
from cascade.domain.common.errors import DomainError, ValidationError
from cascade.domain.governance.aggregate import ServiceLevelObjective
from cascade.domain.governance.aggregate_cost import CostEntry
from cascade.domain.governance.repository import SloQuery, SloSortField
from cascade.domain.governance.value_objects import (
    AssetKind,
    AssetRef,
    ComplianceState,
    CostCategory,
    CostPeriod,
    FreshnessTarget,
    Money,
    Severity,
    SloId,
    SloName,
    SloStatus,
)
from cascade.domain.lakehouse.value_objects import DatasetId
from cascade.domain.serving.repository import ServingViewQuery
from cascade.domain.serving.value_objects import ServingViewId

_logger = structlog.get_logger(__name__)

_MAX_PAGE_SIZE = 100


class GovernanceApplicationService:
    """Coordinates freshness SLOs, cost accounting, and lineage queries."""

    def __init__(self, uow_factory: UnitOfWorkFactory, cost_source: CostSource) -> None:
        self._uow_factory = uow_factory
        self._cost_source = cost_source

    async def register_slo(self, command: RegisterSloCommand) -> SloView:
        name = _build_name(command.name)
        asset = _build_asset(command.asset_kind, command.asset_id)
        target = _build_target(command.max_staleness_minutes)
        severity = _parse_severity(command.severity)

        async with self._uow_factory() as uow:
            if not await _asset_exists(uow, asset):
                raise InputValidationError(f"asset {asset!s} does not exist")
            if await uow.slos.exists_by_name(name):
                raise ConflictError(f"SLO name {name!s} is already in use")
            try:
                slo = ServiceLevelObjective.register(
                    name=name,
                    asset=asset,
                    target=target,
                    severity=severity,
                    owner=command.owner,
                    description=command.description,
                )
            except ValidationError as exc:
                raise InputValidationError(str(exc)) from exc
            await uow.slos.add(slo)
            await uow.commit()
            _emit_slo_events(slo)
            return SloView.from_aggregate(slo)

    async def evaluate_slo(self, slo_id: str) -> SloView:
        identity = SloId.from_string(slo_id)
        now = datetime.now(UTC)
        async with self._uow_factory() as uow:
            slo = await self._load_slo(uow, identity, slo_id)
            last_refresh = await _asset_last_refresh(uow, slo.asset)
            slo.evaluate(last_refresh, now)
            await uow.slos.update(slo)
            await uow.commit()
            _emit_slo_events(slo)
            return SloView.from_aggregate(slo)

    async def evaluate_all(self) -> list[SloView]:
        now = datetime.now(UTC)
        views: list[SloView] = []
        async with self._uow_factory() as uow:
            for slo in await uow.slos.list_active():
                last_refresh = await _asset_last_refresh(uow, slo.asset)
                slo.evaluate(last_refresh, now)
                await uow.slos.update(slo)
                _emit_slo_events(slo)
                views.append(SloView.from_aggregate(slo))
            await uow.commit()
        return views

    async def change_target(self, command: ChangeFreshnessTargetCommand) -> SloView:
        target = _build_target(command.max_staleness_minutes)
        identity = SloId.from_string(command.slo_id)
        async with self._uow_factory() as uow:
            slo = await self._load_slo(uow, identity, command.slo_id)
            slo.change_target(target)
            await uow.slos.update(slo)
            await uow.commit()
            _emit_slo_events(slo)
            return SloView.from_aggregate(slo)

    async def suspend_slo(self, slo_id: str) -> SloView:
        return await self._transition_slo(slo_id, "suspend")

    async def resume_slo(self, slo_id: str) -> SloView:
        return await self._transition_slo(slo_id, "resume")

    async def retire_slo(self, slo_id: str) -> SloView:
        return await self._transition_slo(slo_id, "retire")

    async def get_slo(self, query: GetSloQuery) -> SloView:
        identity = SloId.from_string(query.slo_id)
        async with self._uow_factory() as uow:
            slo = await self._load_slo(uow, identity, query.slo_id)
            return SloView.from_aggregate(slo)

    async def list_slos(self, query: ListSlosQuery) -> Page[SloView]:
        size = _bounded_size(query.size)
        page = max(query.page, 1)
        repo_query = SloQuery(
            asset_kind=_parse_optional_kind(query.asset_kind),
            status=_parse_status(query.status),
            state=_parse_state(query.state),
            offset=(page - 1) * size,
            limit=size,
            sort_by=_parse_sort_field(query.sort_by),
            descending=query.descending,
        )
        async with self._uow_factory() as uow:
            slos, total = await uow.slos.list(repo_query)
            return Page(
                items=[SloView.from_aggregate(s) for s in slos],
                total=total,
                page=page,
                size=size,
            )

    async def record_cost(self, command: RecordCostCommand) -> CostEntryView:
        asset = _build_asset(command.asset_kind, command.asset_id)
        category = _parse_category(command.category)
        try:
            amount = Money(amount_cents=command.amount_cents, currency=command.currency)
            period = CostPeriod(start=command.period_start, end=command.period_end)
        except ValidationError as exc:
            raise InputValidationError(str(exc)) from exc
        async with self._uow_factory() as uow:
            if not await _asset_exists(uow, asset):
                raise InputValidationError(f"asset {asset!s} does not exist")
            entry = CostEntry.record(
                asset=asset,
                category=category,
                amount=amount,
                period=period,
                source=command.source,
            )
            await uow.cost_entries.add(entry)
            await uow.commit()
            _emit_cost_events(entry)
            return CostEntryView.from_aggregate(entry)

    async def import_costs(self, command: ImportCostsCommand) -> ImportResultView:
        if command.window_start >= command.window_end:
            raise InputValidationError("window start must be before window end")
        try:
            observations = await self._cost_source.fetch(command.window_start, command.window_end)
        except CostSourceError as exc:
            raise ConflictError(f"cost source failed: {exc}") from exc

        imported = 0
        total = 0
        async with self._uow_factory() as uow:
            for obs in observations:
                asset = AssetRef(kind=obs.asset_kind, asset_id=obs.asset_id)
                if not await _asset_exists(uow, asset):
                    continue
                try:
                    entry = CostEntry.record(
                        asset=asset,
                        category=obs.category,
                        amount=Money(amount_cents=obs.amount_cents, currency=obs.currency),
                        period=CostPeriod(start=obs.period_start, end=obs.period_end),
                        source="import",
                    )
                except ValidationError:
                    continue
                await uow.cost_entries.add(entry)
                _emit_cost_events(entry)
                imported += 1
                total += obs.amount_cents
            await uow.commit()
        return ImportResultView(imported=imported, total_cents=total)

    async def cost_report(self, query: CostReportQuery) -> CostReportView:
        async with self._uow_factory() as uow:
            summary = await uow.cost_entries.summarize(query.window_start, query.window_end)
            return CostReportView.from_summary(summary)

    async def get_lineage(self, query: GetLineageQuery) -> LineageView:
        kind = _parse_kind(query.asset_kind)
        async with self._uow_factory() as uow:
            nodes: dict[str, LineageNodeView] = {}
            edges: set[tuple[str, str]] = set()
            root = f"{kind.value}:{query.asset_id}"
            await _walk_lineage(uow, kind, query.asset_id, nodes, edges)
            if root not in nodes:
                raise NotFoundError("asset", root)
            return LineageView(
                root=root,
                nodes=list(nodes.values()),
                edges=[LineageEdgeView(from_ref=a, to_ref=b) for a, b in sorted(edges)],
            )

    async def _transition_slo(self, slo_id: str, action: str) -> SloView:
        identity = SloId.from_string(slo_id)
        async with self._uow_factory() as uow:
            slo = await self._load_slo(uow, identity, slo_id)
            try:
                getattr(slo, action)()
            except DomainError as exc:
                raise ConflictError(str(exc)) from exc
            await uow.slos.update(slo)
            await uow.commit()
            _emit_slo_events(slo)
            return SloView.from_aggregate(slo)

    async def _load_slo(
        self, uow: UnitOfWork, identity: SloId, raw_id: str
    ) -> ServiceLevelObjective:
        slo = await uow.slos.get(identity)
        if slo is None:
            raise NotFoundError("SLO", raw_id)
        return slo


async def _walk_lineage(
    uow: UnitOfWork,
    kind: AssetKind,
    asset_id: str,
    nodes: dict[str, LineageNodeView],
    edges: set[tuple[str, str]],
) -> None:
    ref = f"{kind.value}:{asset_id}"
    if ref in nodes:
        return
    if kind is AssetKind.SERVING_VIEW:
        view = await uow.serving_views.get(ServingViewId.from_string(asset_id))
        if view is None:
            return
        nodes[ref] = LineageNodeView(
            kind=kind.value, id=asset_id, name=str(view.name), status=view.status.value
        )
        source_ref = f"{AssetKind.DATASET.value}:{view.source_dataset_id!s}"
        edges.add((source_ref, ref))
        await _walk_lineage(uow, AssetKind.DATASET, str(view.source_dataset_id), nodes, edges)
        return

    dataset = await uow.datasets.get(DatasetId.from_string(asset_id))
    if dataset is None:
        return
    nodes[ref] = LineageNodeView(
        kind=kind.value, id=asset_id, name=str(dataset.name), status=dataset.status.value
    )
    for upstream in dataset.upstreams:
        upstream_ref = f"{AssetKind.DATASET.value}:{upstream.dataset_id!s}"
        edges.add((upstream_ref, ref))
        await _walk_lineage(uow, AssetKind.DATASET, str(upstream.dataset_id), nodes, edges)
    for dependent in await uow.datasets.list_dependents(dataset.id):
        dependent_ref = f"{AssetKind.DATASET.value}:{dependent.id!s}"
        edges.add((ref, dependent_ref))
        await _walk_lineage(uow, AssetKind.DATASET, str(dependent.id), nodes, edges)
    serving_query = ServingViewQuery(source_dataset_id=dataset.id, limit=100)
    serving_views, _ = await uow.serving_views.list(serving_query)
    for view in serving_views:
        view_ref = f"{AssetKind.SERVING_VIEW.value}:{view.id!s}"
        edges.add((ref, view_ref))
        if view_ref not in nodes:
            nodes[view_ref] = LineageNodeView(
                kind=AssetKind.SERVING_VIEW.value,
                id=str(view.id),
                name=str(view.name),
                status=view.status.value,
            )


async def _asset_exists(uow: UnitOfWork, asset: AssetRef) -> bool:
    return await _load_asset_marker(uow, asset) is not None


async def _asset_last_refresh(uow: UnitOfWork, asset: AssetRef) -> datetime | None:
    if asset.kind is AssetKind.DATASET:
        dataset = await uow.datasets.get(DatasetId.from_string(asset.asset_id))
        return dataset.last_materialized_at if dataset is not None else None
    if asset.kind is AssetKind.SERVING_VIEW:
        view = await uow.serving_views.get(ServingViewId.from_string(asset.asset_id))
        return view.last_synced_at if view is not None else None
    return None


async def _load_asset_marker(uow: UnitOfWork, asset: AssetRef) -> object | None:
    try:
        if asset.kind is AssetKind.DATASET:
            return await uow.datasets.get(DatasetId.from_string(asset.asset_id))
        if asset.kind is AssetKind.SERVING_VIEW:
            return await uow.serving_views.get(ServingViewId.from_string(asset.asset_id))
        if asset.kind is AssetKind.STREAM_JOB:
            from cascade.domain.processing.value_objects import StreamJobId

            return await uow.stream_jobs.get(StreamJobId.from_string(asset.asset_id))
        if asset.kind is AssetKind.INGESTION_SOURCE:
            from cascade.domain.ingestion.value_objects import IngestionSourceId

            return await uow.ingestion_sources.get(IngestionSourceId.from_string(asset.asset_id))
        from cascade.domain.pipelines.value_objects import PipelineId

        return await uow.pipelines.get(PipelineId.from_string(asset.asset_id))
    except ValidationError:
        return None


def _build_name(raw: str) -> SloName:
    try:
        return SloName(raw)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_asset(kind_raw: str, asset_id: str) -> AssetRef:
    try:
        return AssetRef(kind=_parse_kind(kind_raw), asset_id=asset_id)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_target(minutes: int) -> FreshnessTarget:
    try:
        return FreshnessTarget(max_staleness_minutes=minutes)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _parse_kind(raw: str) -> AssetKind:
    try:
        return AssetKind(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown asset kind {raw!r}") from exc


def _parse_optional_kind(raw: str | None) -> AssetKind | None:
    return _parse_kind(raw) if raw else None


def _parse_severity(raw: str) -> Severity:
    try:
        return Severity(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown severity {raw!r}") from exc


def _parse_category(raw: str) -> CostCategory:
    try:
        return CostCategory(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown cost category {raw!r}") from exc


def _parse_status(raw: str | None) -> SloStatus | None:
    if raw is None:
        return None
    try:
        return SloStatus(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown SLO status {raw!r}") from exc


def _parse_state(raw: str | None) -> ComplianceState | None:
    if raw is None:
        return None
    try:
        return ComplianceState(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown compliance state {raw!r}") from exc


def _parse_sort_field(raw: str) -> SloSortField:
    try:
        return SloSortField(raw)
    except ValueError as exc:
        raise InputValidationError(f"cannot sort by {raw!r}") from exc


def _bounded_size(size: int) -> int:
    if size < 1:
        return 1
    return min(size, _MAX_PAGE_SIZE)


def _emit_slo_events(slo: ServiceLevelObjective) -> None:
    for event in slo.pull_events():
        _logger.info(
            "domain_event",
            event_type=event.event_type,
            slo_id=str(slo.id),
            occurred_at=event.occurred_at.isoformat(),
        )


def _emit_cost_events(entry: CostEntry) -> None:
    for event in entry.pull_events():
        _logger.info(
            "domain_event",
            event_type=event.event_type,
            cost_entry_id=str(entry.id),
            occurred_at=event.occurred_at.isoformat(),
        )
