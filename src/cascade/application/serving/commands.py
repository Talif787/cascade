from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ColumnInput:
    name: str
    type: str
    role: str
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class RegisterServingViewCommand:
    name: str
    source_dataset_id: str
    engine: str
    columns: tuple[ColumnInput, ...]
    order_by: tuple[str, ...]
    partition_by: str | None = None
    refresh_mode: str = "full"
    refresh_cron: str = "0 * * * *"
    refresh_enabled: bool = True
    description: str = ""


@dataclass(frozen=True, slots=True)
class ChangeRefreshScheduleCommand:
    view_id: str
    refresh_cron: str
    refresh_enabled: bool


@dataclass(frozen=True, slots=True)
class MeasureInput:
    column: str
    aggregation: str


@dataclass(frozen=True, slots=True)
class FilterInput:
    column: str
    op: str
    values: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RunQueryCommand:
    view_id: str
    dimensions: tuple[str, ...] = field(default_factory=tuple)
    measures: tuple[MeasureInput, ...] = field(default_factory=tuple)
    filters: tuple[FilterInput, ...] = field(default_factory=tuple)
    limit: int = 100
