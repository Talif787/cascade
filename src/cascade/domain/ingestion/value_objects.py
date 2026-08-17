from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from cascade.domain.ingestion.errors import (
    InvalidConnectorConfig,
    InvalidDeadLetterPolicy,
    InvalidSourceId,
    InvalidSourceName,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
_MAX_OPTIONS = 100
_MAX_OPTION_LEN = 2048


@dataclass(frozen=True, slots=True)
class IngestionSourceId:
    value: uuid.UUID

    @staticmethod
    def new() -> IngestionSourceId:
        return IngestionSourceId(uuid.uuid4())

    @staticmethod
    def from_string(raw: str) -> IngestionSourceId:
        try:
            return IngestionSourceId(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidSourceId(str(raw)) from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class SourceName:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _NAME_PATTERN.match(self.value):
            raise InvalidSourceName(str(self.value))

    def __str__(self) -> str:
        return self.value


class ConnectorKind(StrEnum):
    POSTGRES_CDC = "postgres_cdc"
    MYSQL_CDC = "mysql_cdc"
    MONGODB_CDC = "mongodb_cdc"
    KAFKA_TOPIC = "kafka_topic"
    HTTP_POLL = "http_poll"
    S3_OBJECT = "s3_object"


class SourceStatus(StrEnum):
    REGISTERED = "registered"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    DECOMMISSIONED = "decommissioned"


class FailureAction(StrEnum):
    DEAD_LETTER = "dead_letter"
    SKIP = "skip"
    HALT = "halt"


@dataclass(frozen=True, slots=True)
class ConnectorConfig:
    options: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.options, Mapping):
            raise InvalidConnectorConfig("connector options must be a mapping")
        if len(self.options) > _MAX_OPTIONS:
            raise InvalidConnectorConfig(f"a connector may declare at most {_MAX_OPTIONS} options")
        for key, value in self.options.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise InvalidConnectorConfig("connector options must be string key/value pairs")
            if not key:
                raise InvalidConnectorConfig("connector option keys must not be empty")
            if len(value) > _MAX_OPTION_LEN:
                raise InvalidConnectorConfig(f"connector option {key!r} is too long")
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))

    def as_dict(self) -> dict[str, str]:
        return dict(self.options)


@dataclass(frozen=True, slots=True)
class DeadLetterPolicy:
    on_failure: FailureAction = FailureAction.DEAD_LETTER
    dlq_topic: str | None = None
    max_retries: int = 3
    tolerance: int = 0

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise InvalidDeadLetterPolicy("max_retries must not be negative")
        if self.tolerance < 0:
            raise InvalidDeadLetterPolicy("tolerance must not be negative")
        if self.on_failure is FailureAction.DEAD_LETTER and not self.dlq_topic:
            raise InvalidDeadLetterPolicy(
                "a dead-letter topic is required when on_failure is dead_letter"
            )

    @property
    def trips_on_breach(self) -> bool:
        return self.tolerance > 0
