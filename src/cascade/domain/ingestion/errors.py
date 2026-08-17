from __future__ import annotations

from cascade.domain.common.errors import InvariantViolation, ValidationError


class InvalidSourceName(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(
            f"invalid source name {value!r}: must be a lowercase slug of 3 to 63 "
            "characters starting with a letter"
        )
        self.value = value


class InvalidSourceId(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid source id {value!r}: must be a UUID")
        self.value = value


class InvalidConnectorConfig(ValidationError):
    """Raised when connector options are malformed."""


class InvalidDeadLetterPolicy(ValidationError):
    """Raised when a dead-letter policy is internally inconsistent."""


class InvalidSourceTransition(InvariantViolation):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot move an ingestion source from {current} to {target}")
        self.current = current
        self.target = target
