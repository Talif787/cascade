from __future__ import annotations

from cascade.application.lakehouse.transformation import TransformationRuntime
from cascade.infrastructure.config import Settings
from cascade.infrastructure.transform.dbt_cloud import DbtCloudTransformationRuntime
from cascade.infrastructure.transform.in_memory import InMemoryTransformationRuntime


def build_transformation_runtime(settings: Settings) -> TransformationRuntime:
    if (
        settings.dbt_cloud_api_url
        and settings.dbt_cloud_account_id
        and settings.dbt_cloud_job_id
        and settings.dbt_cloud_token
    ):
        return DbtCloudTransformationRuntime(
            settings.dbt_cloud_api_url,
            settings.dbt_cloud_account_id,
            settings.dbt_cloud_job_id,
            settings.dbt_cloud_token,
        )
    return InMemoryTransformationRuntime()
