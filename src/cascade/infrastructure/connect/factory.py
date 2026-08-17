from __future__ import annotations

from cascade.application.ingestion.runtime import ConnectorRuntime
from cascade.infrastructure.config import Settings
from cascade.infrastructure.connect.in_memory import InMemoryConnectorRuntime
from cascade.infrastructure.connect.kafka_connect import KafkaConnectRuntime


def build_connector_runtime(settings: Settings) -> ConnectorRuntime:
    if settings.kafka_connect_url:
        return KafkaConnectRuntime(settings.kafka_connect_url)
    return InMemoryConnectorRuntime()
