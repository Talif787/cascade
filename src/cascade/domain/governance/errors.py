from __future__ import annotations

from cascade.domain.common.errors import InvariantViolation, ValidationError


class InvalidSloName(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(
            f"invalid SLO name {value!r}: must be a lowercase slug such as orders-daily-freshness"
        )
        self.value = value


class InvalidSloId(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid SLO id {value!r}: must be a UUID")
        self.value = value


class InvalidCostEntryId(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid cost entry id {value!r}: must be a UUID")
        self.value = value


class InvalidAssetRef(ValidationError):
    """Raised when an asset reference is malformed or the wrong kind."""


class InvalidFreshnessTarget(ValidationError):
    """Raised when a freshness target is not a positive duration."""


class InvalidMoney(ValidationError):
    """Raised when a monetary amount is malformed."""


class InvalidCostPeriod(ValidationError):
    """Raised when a cost period is inverted or empty."""


class InvalidSloTransition(InvariantViolation):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot move an SLO from {current} to {target}")
        self.current = current
        self.target = target
