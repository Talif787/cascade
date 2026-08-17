from __future__ import annotations

from dataclasses import dataclass

from cascade.domain.contracts.value_objects import (
    CompatibilityMode,
    SchemaDefinition,
    SchemaField,
    is_promotable,
)


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    compatible: bool
    mode: CompatibilityMode
    violations: tuple[str, ...] = ()

    @staticmethod
    def ok(mode: CompatibilityMode) -> CompatibilityReport:
        return CompatibilityReport(compatible=True, mode=mode)


def check_compatibility(
    previous: SchemaDefinition, candidate: SchemaDefinition, mode: CompatibilityMode
) -> CompatibilityReport:
    """Assess whether the candidate schema may replace the previous one under a mode."""

    if mode is CompatibilityMode.NONE:
        return CompatibilityReport.ok(mode)

    violations: list[str] = []
    if mode in (CompatibilityMode.BACKWARD, CompatibilityMode.FULL):
        # Backward: the new schema (reader) must read data written with the old schema.
        violations.extend(_read_violations(reader=candidate, writer=previous))
    if mode in (CompatibilityMode.FORWARD, CompatibilityMode.FULL):
        # Forward: the old schema (reader) must read data written with the new schema.
        violations.extend(_read_violations(reader=previous, writer=candidate))

    unique = tuple(dict.fromkeys(violations))
    return CompatibilityReport(compatible=not unique, mode=mode, violations=unique)


def _read_violations(reader: SchemaDefinition, writer: SchemaDefinition) -> list[str]:
    """Violations when a reader schema tries to read data written with a writer schema."""

    violations: list[str] = []
    reader_fields = reader.field_map()
    writer_fields = writer.field_map()

    for name, writer_field in writer_fields.items():
        reader_field = reader_fields.get(name)
        if reader_field is None:
            # The reader dropped a field the writer still emits; harmless, ignored.
            continue
        violations.extend(_field_read_violations(name, reader_field, writer_field))

    for name, reader_field in reader_fields.items():
        if name not in writer_fields and not reader_field.has_effective_default:
            violations.append(
                f"field {name!r} is required by the reader but absent from the writer "
                "and has no default"
            )

    return violations


def _field_read_violations(
    name: str, reader_field: SchemaField, writer_field: SchemaField
) -> list[str]:
    violations: list[str] = []
    if not is_promotable(writer_field.type, reader_field.type):
        violations.append(
            f"field {name!r} type {writer_field.type.value} cannot be read as "
            f"{reader_field.type.value}"
        )
    if writer_field.nullable and not reader_field.nullable:
        violations.append(
            f"field {name!r} is nullable in written data but not in the reading schema"
        )
    return violations
