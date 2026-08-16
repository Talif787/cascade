from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from cascade.domain.pipelines.errors import (
    InvalidConnectorConfig,
    InvalidPipelineId,
    InvalidPipelineName,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
_MAX_RESOURCE_LEN = 512


@dataclass(frozen=True, slots=True)
class PipelineId:
    value: uuid.UUID

    @staticmethod
    def new() -> PipelineId:
        return PipelineId(uuid.uuid4())

    @staticmethod
    def from_string(raw: str) -> PipelineId:
        try:
            return PipelineId(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidPipelineId(str(raw)) from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class PipelineName:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _NAME_PATTERN.match(self.value):
            raise InvalidPipelineName(str(self.value))

    def __str__(self) -> str:
        return self.value


class ConnectorType(StrEnum):
    POSTGRES_CDC = "postgres_cdc"
    KAFKA_TOPIC = "kafka_topic"
    S3 = "s3"
    HTTP_WEBHOOK = "http_webhook"


class SinkType(StrEnum):
    ICEBERG = "iceberg"
    KAFKA_TOPIC = "kafka_topic"
    CLICKHOUSE = "clickhouse"
    WAREHOUSE = "warehouse"


def _normalized_options(options: Mapping[str, str]) -> Mapping[str, str]:
    normalized: dict[str, str] = {}
    for key, value in options.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise InvalidConnectorConfig("connector options must be string key/value pairs")
        normalized[key] = value
    return MappingProxyType(normalized)


def _validate_resource(resource: str) -> str:
    cleaned = resource.strip()
    if not cleaned:
        raise InvalidConnectorConfig("resource identifier is required")
    if len(cleaned) > _MAX_RESOURCE_LEN:
        raise InvalidConnectorConfig("resource identifier is too long")
    return cleaned


@dataclass(frozen=True, slots=True)
class SourceConnector:
    type: ConnectorType
    resource: str
    options: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource", _validate_resource(self.resource))
        object.__setattr__(self, "options", _normalized_options(self.options))


@dataclass(frozen=True, slots=True)
class SinkTarget:
    type: SinkType
    resource: str
    options: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource", _validate_resource(self.resource))
        object.__setattr__(self, "options", _normalized_options(self.options))


class PipelineStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"
