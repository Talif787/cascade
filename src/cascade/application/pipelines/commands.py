from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ConnectorInput:
    type: str
    resource: str
    options: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RegisterPipelineCommand:
    name: str
    source: ConnectorInput
    sink: ConnectorInput
    description: str = ""


@dataclass(frozen=True, slots=True)
class ChangePipelineStatusCommand:
    pipeline_id: str
