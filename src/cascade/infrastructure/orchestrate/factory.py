from __future__ import annotations

from cascade.application.lakehouse.orchestration import Orchestrator
from cascade.infrastructure.config import Settings
from cascade.infrastructure.orchestrate.airflow import AirflowOrchestrator
from cascade.infrastructure.orchestrate.in_memory import InMemoryOrchestrator


def build_orchestrator(settings: Settings) -> Orchestrator:
    if settings.airflow_api_url and settings.airflow_username and settings.airflow_password:
        return AirflowOrchestrator(
            settings.airflow_api_url,
            settings.airflow_username,
            settings.airflow_password,
        )
    return InMemoryOrchestrator()
