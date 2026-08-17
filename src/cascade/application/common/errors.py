from __future__ import annotations


class ApplicationError(Exception):
    """Base class for use-case failures."""


class NotFoundError(ApplicationError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(f"{resource} {identifier!r} was not found")
        self.resource = resource
        self.identifier = identifier


class ConflictError(ApplicationError):
    """Raised when an operation violates a uniqueness or state constraint."""


class InputValidationError(ApplicationError):
    """Raised when a command carries semantically invalid input."""


class ConcurrencyError(ApplicationError):
    """Raised when an optimistic-lock version check fails."""


class PermissionDeniedError(ApplicationError):
    """Raised when a principal lacks a required scope."""


class SchemaIncompatibleError(ApplicationError):
    def __init__(self, mode: str, violations: list[str]) -> None:
        super().__init__(f"schema is not {mode} compatible")
        self.mode = mode
        self.violations = violations
