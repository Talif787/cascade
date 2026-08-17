from __future__ import annotations

from dataclasses import dataclass

from cascade.domain.common.events import DomainEvent
from cascade.domain.serving.value_objects import ServingStatus, ServingViewId


@dataclass(frozen=True, slots=True, kw_only=True)
class ServingViewEvent(DomainEvent):
    view_id: ServingViewId


@dataclass(frozen=True, slots=True, kw_only=True)
class ServingViewRegistered(ServingViewEvent):
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SyncStarted(ServingViewEvent):
    sync_ref: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ServingViewSynced(ServingViewEvent):
    sync_ref: str
    row_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SyncFailed(ServingViewEvent):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ServingViewStatusChanged(ServingViewEvent):
    previous: ServingStatus
    current: ServingStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class RefreshScheduleChanged(ServingViewEvent):
    enabled: bool
