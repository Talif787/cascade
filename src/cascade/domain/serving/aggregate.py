from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import AggregateRoot, utcnow
from cascade.domain.lakehouse.value_objects import DatasetId
from cascade.domain.serving.errors import (
    InvalidQuery,
    InvalidServingEngine,
    InvalidServingTransition,
    ViewNotQueryable,
)
from cascade.domain.serving.events import (
    RefreshScheduleChanged,
    ServingViewRegistered,
    ServingViewStatusChanged,
    ServingViewSynced,
    SyncFailed,
    SyncStarted,
)
from cascade.domain.serving.value_objects import (
    ClickHouseEngine,
    ColumnRole,
    ExposedSchema,
    QueryPlan,
    QueryRequest,
    RefreshMode,
    ServingStatus,
    ServingViewId,
    ServingViewName,
)

_MAX_DESCRIPTION_LEN = 1024

_QUERYABLE = frozenset({ServingStatus.READY, ServingStatus.STALE})

_ALLOWED_TRANSITIONS: dict[ServingStatus, frozenset[ServingStatus]] = {
    ServingStatus.REGISTERED: frozenset({ServingStatus.SYNCING, ServingStatus.RETIRED}),
    ServingStatus.SYNCING: frozenset(
        {ServingStatus.READY, ServingStatus.FAILED, ServingStatus.RETIRED}
    ),
    ServingStatus.READY: frozenset(
        {ServingStatus.SYNCING, ServingStatus.STALE, ServingStatus.RETIRED}
    ),
    ServingStatus.STALE: frozenset({ServingStatus.SYNCING, ServingStatus.RETIRED}),
    ServingStatus.FAILED: frozenset({ServingStatus.SYNCING, ServingStatus.RETIRED}),
    ServingStatus.RETIRED: frozenset(),
}


class ServingView(AggregateRoot[ServingViewId]):
    """A ClickHouse-backed view that serves curated data to the analytics layer."""

    def __init__(
        self,
        view_id: ServingViewId,
        *,
        name: ServingViewName,
        source_dataset_id: DatasetId,
        engine: ClickHouseEngine,
        schema: ExposedSchema,
        refresh_mode: RefreshMode,
        refresh_cron: str,
        refresh_enabled: bool,
        status: ServingStatus,
        last_sync_ref: str | None,
        last_row_count: int | None,
        last_synced_at: datetime | None,
        synced_source_at: datetime | None,
        description: str,
        created_at: datetime,
        updated_at: datetime,
        version: int = 0,
    ) -> None:
        super().__init__(view_id, version=version)
        self._name = name
        self._source_dataset_id = source_dataset_id
        self._engine = engine
        self._schema = schema
        self._refresh_mode = refresh_mode
        self._refresh_cron = refresh_cron
        self._refresh_enabled = refresh_enabled
        self._status = status
        self._last_sync_ref = last_sync_ref
        self._last_row_count = last_row_count
        self._last_synced_at = last_synced_at
        self._synced_source_at = synced_source_at
        self._description = description
        self._created_at = created_at
        self._updated_at = updated_at

    @classmethod
    def register(
        cls,
        *,
        name: ServingViewName,
        source_dataset_id: DatasetId,
        engine: ClickHouseEngine,
        schema: ExposedSchema,
        refresh_mode: RefreshMode,
        refresh_cron: str = "0 * * * *",
        refresh_enabled: bool = True,
        description: str = "",
    ) -> ServingView:
        if schema.requires_measure(engine) and not schema.has_measure():
            raise InvalidServingEngine(
                f"the {engine.value} engine requires at least one measure column"
            )
        now = utcnow()
        view = cls(
            ServingViewId.new(),
            name=name,
            source_dataset_id=source_dataset_id,
            engine=engine,
            schema=schema,
            refresh_mode=refresh_mode,
            refresh_cron=refresh_cron,
            refresh_enabled=refresh_enabled,
            status=ServingStatus.REGISTERED,
            last_sync_ref=None,
            last_row_count=None,
            last_synced_at=None,
            synced_source_at=None,
            description=description.strip()[:_MAX_DESCRIPTION_LEN],
            created_at=now,
            updated_at=now,
        )
        view._record(ServingViewRegistered(view_id=view.id, name=str(name)))
        return view

    @property
    def name(self) -> ServingViewName:
        return self._name

    @property
    def source_dataset_id(self) -> DatasetId:
        return self._source_dataset_id

    @property
    def engine(self) -> ClickHouseEngine:
        return self._engine

    @property
    def schema(self) -> ExposedSchema:
        return self._schema

    @property
    def refresh_mode(self) -> RefreshMode:
        return self._refresh_mode

    @property
    def refresh_cron(self) -> str:
        return self._refresh_cron

    @property
    def refresh_enabled(self) -> bool:
        return self._refresh_enabled

    @property
    def status(self) -> ServingStatus:
        return self._status

    @property
    def last_sync_ref(self) -> str | None:
        return self._last_sync_ref

    @property
    def last_row_count(self) -> int | None:
        return self._last_row_count

    @property
    def last_synced_at(self) -> datetime | None:
        return self._last_synced_at

    @property
    def synced_source_at(self) -> datetime | None:
        return self._synced_source_at

    @property
    def description(self) -> str:
        return self._description

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def begin_sync(self, sync_ref: str) -> None:
        self._transition_to(ServingStatus.SYNCING)
        self._last_sync_ref = sync_ref
        self._record(SyncStarted(view_id=self.id, sync_ref=sync_ref))

    def complete_sync(self, sync_ref: str, row_count: int, source_at: datetime | None) -> None:
        self._last_sync_ref = sync_ref
        self._last_row_count = row_count
        self._last_synced_at = utcnow()
        self._synced_source_at = source_at
        self._transition_to(ServingStatus.READY)
        self._record(ServingViewSynced(view_id=self.id, sync_ref=sync_ref, row_count=row_count))

    def fail_sync(self, reason: str) -> None:
        self._transition_to(ServingStatus.FAILED)
        self._record(SyncFailed(view_id=self.id, reason=reason))

    def reconcile(self, source_materialized_at: datetime | None) -> bool:
        if self._status is not ServingStatus.READY:
            return False
        if source_materialized_at is None:
            return False
        if self._synced_source_at is None or source_materialized_at > self._synced_source_at:
            self._transition_to(ServingStatus.STALE)
            return True
        return False

    def change_schedule(self, cron: str, enabled: bool) -> None:
        self._refresh_cron = cron
        self._refresh_enabled = enabled
        self._touch()
        self._record(RefreshScheduleChanged(view_id=self.id, enabled=enabled))

    def retire(self) -> None:
        self._transition_to(ServingStatus.RETIRED)

    def plan_query(self, request: QueryRequest) -> QueryPlan:
        if self._status not in _QUERYABLE:
            raise ViewNotQueryable(self._status.value)
        for name in request.dimensions:
            column = self._schema.column(name)
            if column is None:
                raise InvalidQuery(f"unknown dimension {name!r}")
            if column.role is ColumnRole.MEASURE:
                raise InvalidQuery(f"column {name!r} is a measure, not a dimension")
        for measure in request.measures:
            column = self._schema.column(measure.column)
            if column is None:
                raise InvalidQuery(f"unknown measure {measure.column!r}")
            if column.role is not ColumnRole.MEASURE:
                raise InvalidQuery(f"column {measure.column!r} is not a measure")
        for clause in request.filters:
            if self._schema.column(clause.column) is None:
                raise InvalidQuery(f"unknown filter column {clause.column!r}")
        limit = max(1, min(request.limit, 10_000))
        return QueryPlan(
            table=str(self._name),
            dimensions=request.dimensions,
            measures=request.measures,
            filters=request.filters,
            limit=limit,
        )

    def _transition_to(self, target: ServingStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self._status]:
            raise InvalidServingTransition(self._status.value, target.value)
        previous = self._status
        self._status = target
        self._touch()
        self._record(ServingViewStatusChanged(view_id=self.id, previous=previous, current=target))

    def _touch(self) -> None:
        self._updated_at = utcnow()
