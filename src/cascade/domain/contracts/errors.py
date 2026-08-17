from __future__ import annotations

from cascade.domain.common.errors import DomainError, InvariantViolation, ValidationError


class InvalidContractName(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(
            f"invalid contract name {value!r}: must be a lowercase slug of 3 to 63 "
            "characters starting with a letter"
        )
        self.value = value


class InvalidContractId(ValidationError):
    def __init__(self, value: str) -> None:
        super().__init__(f"invalid contract id {value!r}: must be a UUID")
        self.value = value


class InvalidSchemaDefinition(ValidationError):
    """Raised when a schema has no fields or duplicate field names."""


class SchemaVersionNotFound(DomainError):
    def __init__(self, version: int) -> None:
        super().__init__(f"schema version {version} does not exist on this contract")
        self.version = version


class IncompatibleSchema(InvariantViolation):
    def __init__(self, mode: str, violations: list[str]) -> None:
        joined = "; ".join(violations)
        super().__init__(f"schema is not {mode} compatible: {joined}")
        self.mode = mode
        self.violations = violations


class ContractAlreadyDeprecated(InvariantViolation):
    def __init__(self) -> None:
        super().__init__("cannot publish a new version to a deprecated contract")
