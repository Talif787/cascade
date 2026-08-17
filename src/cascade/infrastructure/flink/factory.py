from __future__ import annotations

from cascade.application.processing.runtime import FlinkRuntime
from cascade.infrastructure.config import Settings
from cascade.infrastructure.flink.flink_rest import FlinkRestRuntime
from cascade.infrastructure.flink.in_memory import InMemoryFlinkRuntime


def build_flink_runtime(settings: Settings) -> FlinkRuntime:
    if settings.flink_rest_url and settings.flink_jar_id:
        return FlinkRestRuntime(
            settings.flink_rest_url,
            settings.flink_jar_id,
            settings.flink_entry_class,
        )
    return InMemoryFlinkRuntime()
