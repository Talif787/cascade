from __future__ import annotations

from datetime import UTC, datetime

from cascade.domain.common.events import DomainEvent


def utcnow() -> datetime:
    return datetime.now(UTC)


class Entity[TId]:
    """An object defined by identity rather than attributes."""

    def __init__(self, entity_id: TId) -> None:
        self._id = entity_id

    @property
    def id(self) -> TId:
        return self._id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity) or type(other) is not type(self):
            return NotImplemented
        return bool(self._id == other._id)

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._id))


class AggregateRoot[TId](Entity[TId]):
    """Consistency boundary that records domain events and tracks a version."""

    def __init__(self, entity_id: TId, version: int = 0) -> None:
        super().__init__(entity_id)
        self._version = version
        self._events: list[DomainEvent] = []

    @property
    def version(self) -> int:
        return self._version

    def _record(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events
