from __future__ import annotations

from cascade.application.governance.cost_source import CostSource
from cascade.infrastructure.config import Settings
from cascade.infrastructure.cost.http import HttpCostSource
from cascade.infrastructure.cost.in_memory import InMemoryCostSource


def build_cost_source(settings: Settings) -> CostSource:
    if settings.cost_source_url:
        return HttpCostSource(settings.cost_source_url, settings.cost_source_token)
    return InMemoryCostSource()
