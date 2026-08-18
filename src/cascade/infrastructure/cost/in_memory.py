from __future__ import annotations

from datetime import datetime

from cascade.application.governance.cost_source import CostObservation, CostSource
from cascade.domain.governance.value_objects import AssetKind, CostCategory


class InMemoryCostSource(CostSource):
    """Returns a fixed set of synthetic cost observations for local development.

    The observations are seeded from a static list so the cost report has data
    without a billing integration. Only observations whose assets exist are kept
    by the caller, so this can be primed with representative asset ids.
    """

    def __init__(self, observations: tuple[CostObservation, ...] = ()) -> None:
        self._observations = observations

    def with_observations(self, observations: tuple[CostObservation, ...]) -> InMemoryCostSource:
        return InMemoryCostSource(observations)

    async def fetch(
        self, window_start: datetime, window_end: datetime
    ) -> tuple[CostObservation, ...]:
        return tuple(
            obs
            for obs in self._observations
            if obs.period_start >= window_start and obs.period_end <= window_end
        )


def synthetic_observations_for(
    asset_kind: AssetKind, asset_id: str, window_start: datetime, window_end: datetime
) -> tuple[CostObservation, ...]:
    """Build a compute and a storage observation for one asset over a window."""

    return (
        CostObservation(
            asset_kind=asset_kind,
            asset_id=asset_id,
            category=CostCategory.COMPUTE,
            amount_cents=1234,
            currency="USD",
            period_start=window_start,
            period_end=window_end,
        ),
        CostObservation(
            asset_kind=asset_kind,
            asset_id=asset_id,
            category=CostCategory.STORAGE,
            amount_cents=567,
            currency="USD",
            period_start=window_start,
            period_end=window_end,
        ),
    )
