from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import AggregateRoot, utcnow
from cascade.domain.governance.events import CostRecorded
from cascade.domain.governance.value_objects import (
    AssetRef,
    CostCategory,
    CostEntryId,
    CostPeriod,
    Money,
)


class CostEntry(AggregateRoot[CostEntryId]):
    """An immutable record of cost attributed to an asset over a period."""

    def __init__(
        self,
        cost_entry_id: CostEntryId,
        *,
        asset: AssetRef,
        category: CostCategory,
        amount: Money,
        period: CostPeriod,
        source: str,
        recorded_at: datetime,
        version: int = 0,
    ) -> None:
        super().__init__(cost_entry_id, version=version)
        self._asset = asset
        self._category = category
        self._amount = amount
        self._period = period
        self._source = source
        self._recorded_at = recorded_at

    @classmethod
    def record(
        cls,
        *,
        asset: AssetRef,
        category: CostCategory,
        amount: Money,
        period: CostPeriod,
        source: str = "manual",
    ) -> CostEntry:
        entry = cls(
            CostEntryId.new(),
            asset=asset,
            category=category,
            amount=amount,
            period=period,
            source=source.strip() or "manual",
            recorded_at=utcnow(),
        )
        entry._record(
            CostRecorded(
                cost_entry_id=entry.id,
                asset=str(asset),
                amount_cents=amount.amount_cents,
            )
        )
        return entry

    @property
    def asset(self) -> AssetRef:
        return self._asset

    @property
    def category(self) -> CostCategory:
        return self._category

    @property
    def amount(self) -> Money:
        return self._amount

    @property
    def period(self) -> CostPeriod:
        return self._period

    @property
    def source(self) -> str:
        return self._source

    @property
    def recorded_at(self) -> datetime:
        return self._recorded_at
