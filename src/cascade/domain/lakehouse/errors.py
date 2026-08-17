from __future__ import annotations

from cascade.domain.common.errors import InvariantViolation, ValidationError


class InvalidDatasetName(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(
            f"invalid dataset name {value!r}: must be a dotted identifier such as "
            "silver.orders_enriched"
        )
        self.value = value


class InvalidDatasetId(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid dataset id {value!r}: must be a UUID")
        self.value = value


class InvalidTransformation(ValidationError):
    """Raised when a transformation definition is malformed."""


class InvalidSchedule(ValidationError):
    """Raised when a schedule is malformed."""


class InvalidQualityCheck(ValidationError):
    """Raised when a data-quality check is malformed."""


class InvalidMedallionDependency(ValidationError):
    """Raised when a dataset depends on a higher medallion layer or on itself."""


class InvalidDatasetTransition(InvariantViolation):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot move a dataset from {current} to {target}")
        self.current = current
        self.target = target
