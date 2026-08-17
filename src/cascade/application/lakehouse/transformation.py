from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from cascade.domain.lakehouse.value_objects import (
    Materialization,
    MedallionLayer,
    QualityCheck,
    TransformationEngine,
)


class TransformationRuntimeError(RuntimeError):
    """Raised when the transformation runtime cannot satisfy a request."""


@dataclass(frozen=True, slots=True)
class TransformationSpec:
    name: str
    layer: MedallionLayer
    engine: TransformationEngine
    identifier: str
    materialization: Materialization
    quality_checks: tuple[QualityCheck, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class QualityOutcomeDTO:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class TransformationResult:
    run_ref: str
    row_count: int
    quality: tuple[QualityOutcomeDTO, ...] = field(default_factory=tuple)


class TransformationRuntime(ABC):
    """Port for the engine (dbt) that materializes medallion tables."""

    @abstractmethod
    async def run(self, spec: TransformationSpec) -> TransformationResult: ...
