from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_INTEGRAL = ("int", "long", "date", "timestamp")
_FLOATING = ("float", "double")


class RecordValidationError(ValueError):
    """Raised when a record does not satisfy the resolved schema."""

    def __init__(self, violations: list[str]) -> None:
        super().__init__("; ".join(violations))
        self.violations = violations


@dataclass(frozen=True, slots=True)
class SchemaFieldSpec:
    name: str
    type: str
    nullable: bool = False
    has_default: bool = False


@dataclass(frozen=True, slots=True)
class ResolvedSchema:
    contract_id: str
    contract_name: str
    version: int
    registry_id: int | None
    fields: tuple[SchemaFieldSpec, ...]

    def validate_record(self, record: dict[str, Any]) -> None:
        violations = self.check_record(record)
        if violations:
            raise RecordValidationError(violations)

    def check_record(self, record: dict[str, Any]) -> list[str]:
        violations: list[str] = []
        known = {field.name for field in self.fields}
        for field in self.fields:
            if field.name not in record:
                if not (field.has_default or field.nullable):
                    violations.append(f"missing required field {field.name!r}")
                continue
            value = record[field.name]
            if value is None:
                if not field.nullable:
                    violations.append(f"field {field.name!r} must not be null")
                continue
            if not _type_matches(field.type, value):
                violations.append(
                    f"field {field.name!r} expected {field.type} but got {type(value).__name__}"
                )
        for key in record:
            if key not in known:
                violations.append(f"unexpected field {key!r} not declared in the contract")
        return violations


def _type_matches(field_type: str, value: Any) -> bool:
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type in _INTEGRAL:
        if field_type in ("date", "timestamp") and isinstance(value, str):
            return True
        return isinstance(value, int) and not isinstance(value, bool)
    if field_type in _FLOATING:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if field_type == "string":
        return isinstance(value, str)
    if field_type == "bytes":
        return isinstance(value, (bytes, bytearray))
    return False
