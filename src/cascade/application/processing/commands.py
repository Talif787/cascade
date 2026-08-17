from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EndpointInput:
    kind: str
    resource: str


@dataclass(frozen=True, slots=True)
class CheckpointInput:
    interval_ms: int = 60_000
    timeout_ms: int = 600_000
    min_pause_ms: int = 0
    max_concurrent: int = 1


@dataclass(frozen=True, slots=True)
class RestartInput:
    kind: str = "fixed_delay"
    attempts: int = 3
    delay_ms: int = 10_000


@dataclass(frozen=True, slots=True)
class DefineJobCommand:
    name: str
    source: EndpointInput
    sink: EndpointInput
    delivery_guarantee: str = "exactly_once"
    checkpoint: CheckpointInput = field(default_factory=CheckpointInput)
    restart: RestartInput = field(default_factory=RestartInput)
    parallelism: int = 1
    contract_id: str | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class ChangeCheckpointConfigCommand:
    job_id: str
    checkpoint: CheckpointInput
