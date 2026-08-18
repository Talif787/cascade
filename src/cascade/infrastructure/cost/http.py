from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from cascade.application.governance.cost_source import (
    CostObservation,
    CostSource,
    CostSourceError,
)
from cascade.domain.governance.value_objects import AssetKind, CostCategory


class HttpCostSource(CostSource):
    """Adapter that pulls cost observations from a billing export endpoint.

    The endpoint is expected to return a JSON list of observations, each with an
    asset kind and id, a category, an amount in cents, and a period.
    """

    def __init__(
        self, base_url: str, token: str | None = None, timeout_seconds: float = 30.0
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds

    async def fetch(
        self, window_start: datetime, window_end: datetime
    ) -> tuple[CostObservation, ...]:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        params = {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}/costs", params=params, headers=headers)
        if response.status_code >= 400:
            raise CostSourceError(f"cost export failed: {response.status_code} {response.text}")
        payload: list[dict[str, Any]] = response.json()
        return tuple(_parse(item) for item in payload)


def _parse(item: dict[str, Any]) -> CostObservation:
    return CostObservation(
        asset_kind=AssetKind(item["asset_kind"]),
        asset_id=str(item["asset_id"]),
        category=CostCategory(item["category"]),
        amount_cents=int(item["amount_cents"]),
        currency=str(item.get("currency", "USD")),
        period_start=datetime.fromisoformat(item["period_start"]),
        period_end=datetime.fromisoformat(item["period_end"]),
    )
