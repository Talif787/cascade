from __future__ import annotations

from cascade.application.serving.runtime import ClickHouseRuntime
from cascade.infrastructure.clickhouse.http import ClickHouseHttpRuntime
from cascade.infrastructure.clickhouse.in_memory import InMemoryClickHouseRuntime
from cascade.infrastructure.config import Settings


def build_clickhouse_runtime(settings: Settings) -> ClickHouseRuntime:
    if settings.clickhouse_url:
        return ClickHouseHttpRuntime(
            settings.clickhouse_url,
            settings.clickhouse_database,
            settings.clickhouse_username,
            settings.clickhouse_password,
        )
    return InMemoryClickHouseRuntime()
