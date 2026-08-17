from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from cascade.domain.processing.errors import (
    InvalidCheckpointConfig,
    InvalidJobEndpoint,
    InvalidJobId,
    InvalidJobName,
    InvalidRestartStrategy,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
_MAX_RESOURCE_LEN = 512


@dataclass(frozen=True, slots=True)
class StreamJobId:
    value: uuid.UUID

    @staticmethod
    def new() -> StreamJobId:
        return StreamJobId(uuid.uuid4())

    @staticmethod
    def from_string(raw: str) -> StreamJobId:
        try:
            return StreamJobId(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidJobId(str(raw)) from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class JobName:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _NAME_PATTERN.match(self.value):
            raise InvalidJobName(str(self.value))

    def __str__(self) -> str:
        return self.value


class JobStatus(StrEnum):
    DEFINED = "defined"
    SUBMITTED = "submitted"
    RUNNING = "running"
    RESTARTING = "restarting"
    SUSPENDED = "suspended"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeliveryGuarantee(StrEnum):
    EXACTLY_ONCE = "exactly_once"
    AT_LEAST_ONCE = "at_least_once"


class SourceKind(StrEnum):
    KAFKA_TOPIC = "kafka_topic"
    INGESTION_SOURCE = "ingestion_source"


class SinkKind(StrEnum):
    ICEBERG = "iceberg"
    KAFKA_TOPIC = "kafka_topic"
    JDBC = "jdbc"


class RestartKind(StrEnum):
    NONE = "none"
    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_DELAY = "exponential_delay"
    FAILURE_RATE = "failure_rate"


_EXACTLY_ONCE_SINKS = frozenset({SinkKind.ICEBERG})


@dataclass(frozen=True, slots=True)
class JobSource:
    kind: SourceKind
    resource: str

    def __post_init__(self) -> None:
        if not isinstance(self.resource, str) or not self.resource.strip():
            raise InvalidJobEndpoint("job source resource is required")
        if len(self.resource) > _MAX_RESOURCE_LEN:
            raise InvalidJobEndpoint("job source resource is too long")


@dataclass(frozen=True, slots=True)
class JobSink:
    kind: SinkKind
    resource: str

    def __post_init__(self) -> None:
        if not isinstance(self.resource, str) or not self.resource.strip():
            raise InvalidJobEndpoint("job sink resource is required")
        if len(self.resource) > _MAX_RESOURCE_LEN:
            raise InvalidJobEndpoint("job sink resource is too long")

    @property
    def requires_exactly_once(self) -> bool:
        return self.kind in _EXACTLY_ONCE_SINKS


@dataclass(frozen=True, slots=True)
class CheckpointConfig:
    interval_ms: int = 60_000
    timeout_ms: int = 600_000
    min_pause_ms: int = 0
    max_concurrent: int = 1

    def __post_init__(self) -> None:
        if self.interval_ms <= 0:
            raise InvalidCheckpointConfig("checkpoint interval must be positive")
        if self.timeout_ms <= 0:
            raise InvalidCheckpointConfig("checkpoint timeout must be positive")
        if self.min_pause_ms < 0:
            raise InvalidCheckpointConfig("minimum pause must not be negative")
        if self.max_concurrent < 1:
            raise InvalidCheckpointConfig("at least one concurrent checkpoint is required")

    @property
    def enabled(self) -> bool:
        return self.interval_ms > 0


@dataclass(frozen=True, slots=True)
class RestartStrategy:
    kind: RestartKind = RestartKind.FIXED_DELAY
    attempts: int = 3
    delay_ms: int = 10_000

    def __post_init__(self) -> None:
        if self.attempts < 0:
            raise InvalidRestartStrategy("restart attempts must not be negative")
        if self.delay_ms < 0:
            raise InvalidRestartStrategy("restart delay must not be negative")
