from __future__ import annotations

from cascade.domain.common.errors import InvariantViolation, ValidationError


class InvalidJobName(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(
            f"invalid job name {value!r}: must be a lowercase slug of 3 to 63 "
            "characters starting with a letter"
        )
        self.value = value


class InvalidJobId(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid job id {value!r}: must be a UUID")
        self.value = value


class InvalidCheckpointConfig(ValidationError):
    """Raised when a checkpoint configuration is inconsistent."""


class InvalidRestartStrategy(ValidationError):
    """Raised when a restart strategy is inconsistent."""


class InvalidJobEndpoint(ValidationError):
    """Raised when a job source or sink is malformed."""


class ExactlyOnceRequired(ValidationError):
    """Raised when a sink that needs exactly-once is not configured for it."""


class InvalidJobTransition(InvariantViolation):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot move a stream job from {current} to {target}")
        self.current = current
        self.target = target
