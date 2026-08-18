from __future__ import annotations

from cascade.domain.common.errors import InvariantViolation, ValidationError


class InvalidQuestion(ValidationError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"invalid question: {reason}")


class InvalidCopilotQueryId(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid copilot query id {value!r}: must be a UUID")
        self.value = value


class InvalidTranslation(ValidationError):
    """Raised when a translated query is structurally invalid."""


class InvalidCopilotTransition(InvariantViolation):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"cannot move a copilot query from {current} to {target}")
        self.current = current
        self.target = target
