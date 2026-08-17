from __future__ import annotations

from cascade.domain.common.errors import InvariantViolation, ValidationError


class InvalidServingViewName(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(
            f"invalid serving view name {value!r}: must be a dotted identifier such as "
            "analytics.orders_daily"
        )
        self.value = value


class InvalidServingViewId(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid serving view id {value!r}: must be a UUID")
        self.value = value


class InvalidColumn(ValidationError):
    """Raised when a served column is malformed."""


class InvalidExposedSchema(ValidationError):
    """Raised when the set of served columns is inconsistent."""


class InvalidRefreshConfig(ValidationError):
    """Raised when a refresh configuration is inconsistent."""


class InvalidServingEngine(ValidationError):
    """Raised when the engine is incompatible with the declared columns."""


class InvalidQuery(ValidationError):
    """Raised when an analytics query references undeclared columns or roles."""


class InvalidServingTransition(InvariantViolation):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot move a serving view from {current} to {target}")
        self.current = current
        self.target = target


class ViewNotQueryable(InvariantViolation):
    def __init__(self, status: str) -> None:
        super().__init__(f"a serving view in status {status} cannot be queried")
        self.status = status
