from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CASCADE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "cascade-control-plane"
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    log_json: bool = True

    http_host: str = "0.0.0.0"
    http_port: int = 8000
    root_path: str = ""

    database_url: str = "postgresql+asyncpg://cascade:cascade@localhost:5432/cascade"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30
    database_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    schema_registry_url: str | None = None
    default_compatibility_mode: str = "backward"

    kafka_connect_url: str | None = None

    flink_rest_url: str | None = None
    flink_jar_id: str | None = None
    flink_entry_class: str | None = None

    dbt_cloud_api_url: str | None = None
    dbt_cloud_account_id: str | None = None
    dbt_cloud_job_id: str | None = None
    dbt_cloud_token: str | None = None

    airflow_api_url: str | None = None
    airflow_username: str | None = None
    airflow_password: str | None = None

    clickhouse_url: str | None = None
    clickhouse_database: str = "default"
    clickhouse_username: str = "default"
    clickhouse_password: str = ""

    jwt_algorithm: str = "HS256"
    jwt_secret: str = "change-me-in-production"
    jwt_jwks_url: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    auth_enabled: bool = True

    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120
    rate_limit_burst: int = 40

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"

    idempotency_ttl_seconds: int = 86_400
    cache_ttl_seconds: int = 60

    @field_validator("log_level")
    @classmethod
    def _normalize_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid log level {value!r}")
        return normalized

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
