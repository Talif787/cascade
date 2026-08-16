from __future__ import annotations

from cascade.domain.common.errors import InvariantViolation, ValidationError


class InvalidPipelineName(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(
            f"invalid pipeline name {value!r}: must be a lowercase slug of 3 to 63 "
            "characters starting with a letter"
        )
        self.value = value


class InvalidPipelineId(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid pipeline id {value!r}: must be a UUID")
        self.value = value


class InvalidConnectorConfig(ValidationError):
    """Raised when a source or sink configuration is malformed."""


class InvalidStateTransition(InvariantViolation):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot transition pipeline from {current} to {target}")
        self.current = current
        self.target = target
