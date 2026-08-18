from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from cascade.domain.governance.value_objects import AssetKind, CostCategory


class CostSourceError(RuntimeError):
    """Raised when the cost source cannot be read."""


@dataclass(frozen=True, slots=True)
class CostObservation:
    asset_kind: AssetKind
    asset_id: str
    category: CostCategory
    amount_cents: int
    currency: str
    period_start: datetime
    period_end: datetime


class CostSource(ABC):
    """Port for a billing source that reports cost observations per asset."""

    @abstractmethod
    async def fetch(
        self, window_start: datetime, window_end: datetime
    ) -> tuple[CostObservation, ...]: ...
