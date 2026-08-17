from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DeadLetterInput:
    on_failure: str = "dead_letter"
    dlq_topic: str | None = None
    max_retries: int = 3
    tolerance: int = 0


@dataclass(frozen=True, slots=True)
class RegisterSourceCommand:
    name: str
    connector_kind: str
    config: dict[str, str] = field(default_factory=dict)
    contract_id: str = ""
    pipeline_id: str | None = None
    dead_letter: DeadLetterInput = field(default_factory=DeadLetterInput)
    description: str = ""


@dataclass(frozen=True, slots=True)
class RecordDeadLettersCommand:
    source_id: str
    count: int


@dataclass(frozen=True, slots=True)
class ChangeDeadLetterPolicyCommand:
    source_id: str
    dead_letter: DeadLetterInput
