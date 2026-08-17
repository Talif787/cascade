from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TransformationInput:
    engine: str = "dbt"
    identifier: str = ""
    materialization: str = "table"


@dataclass(frozen=True, slots=True)
class ScheduleInput:
    cron: str = "0 * * * *"
    timezone: str = "UTC"
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class QualityCheckInput:
    kind: str
    column: str | None = None
    threshold: int | None = None
    accepted_values: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RegisterDatasetCommand:
    name: str
    layer: str
    transformation: TransformationInput
    schedule: ScheduleInput = field(default_factory=ScheduleInput)
    upstream_ids: tuple[str, ...] = field(default_factory=tuple)
    quality_checks: tuple[QualityCheckInput, ...] = field(default_factory=tuple)
    contract_id: str | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class ChangeScheduleCommand:
    dataset_id: str
    schedule: ScheduleInput
