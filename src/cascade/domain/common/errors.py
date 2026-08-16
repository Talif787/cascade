from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain rule violations."""


class ValidationError(DomainError):
    """Raised when a value object or invariant fails validation."""


class InvariantViolation(DomainError):
    """Raised when an aggregate operation would break an invariant."""
