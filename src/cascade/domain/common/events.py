from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Base class for facts that have happened within the domain."""

    occurred_at: datetime = field(default_factory=_now)

    @property
    def event_type(self) -> str:
        return type(self).__name__
