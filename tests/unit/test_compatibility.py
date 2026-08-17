from __future__ import annotations

from cascade.domain.contracts.compatibility import check_compatibility
from cascade.domain.contracts.value_objects import (
    CompatibilityMode,
    FieldType,
    SchemaDefinition,
    SchemaField,
)


def _schema(*fields: SchemaField) -> SchemaDefinition:
    return SchemaDefinition(fields=fields)


def _f(
    name: str, type_: FieldType, *, nullable: bool = False, has_default: bool = False
) -> SchemaField:
    return SchemaField(name=name, type=type_, nullable=nullable, has_default=has_default)


BASE = _schema(_f("id", FieldType.LONG), _f("name", FieldType.STRING))


def test_none_mode_is_always_compatible() -> None:
    stripped = _schema(_f("id", FieldType.INT))
    report = check_compatibility(BASE, stripped, CompatibilityMode.NONE)
    assert report.compatible


def test_backward_allows_removing_a_field() -> None:
    candidate = _schema(_f("id", FieldType.LONG))
    assert check_compatibility(BASE, candidate, CompatibilityMode.BACKWARD).compatible


def test_backward_allows_adding_a_field_with_default() -> None:
    candidate = _schema(
        _f("id", FieldType.LONG),
        _f("name", FieldType.STRING),
        _f("email", FieldType.STRING, has_default=True),
    )
    assert check_compatibility(BASE, candidate, CompatibilityMode.BACKWARD).compatible


def test_backward_rejects_adding_a_required_field() -> None:
    candidate = _schema(
        _f("id", FieldType.LONG),
        _f("name", FieldType.STRING),
        _f("email", FieldType.STRING),
    )
    report = check_compatibility(BASE, candidate, CompatibilityMode.BACKWARD)
    assert not report.compatible
    assert any("email" in v for v in report.violations)


def test_backward_allows_widening_type() -> None:
    narrow = _schema(_f("id", FieldType.INT))
    wide = _schema(_f("id", FieldType.LONG))
    assert check_compatibility(narrow, wide, CompatibilityMode.BACKWARD).compatible


def test_backward_rejects_narrowing_type() -> None:
    wide = _schema(_f("id", FieldType.LONG))
    narrow = _schema(_f("id", FieldType.INT))
    assert not check_compatibility(wide, narrow, CompatibilityMode.BACKWARD).compatible


def test_forward_allows_adding_a_required_field() -> None:
    candidate = _schema(
        _f("id", FieldType.LONG),
        _f("name", FieldType.STRING),
        _f("email", FieldType.STRING),
    )
    assert check_compatibility(BASE, candidate, CompatibilityMode.FORWARD).compatible


def test_forward_rejects_removing_a_required_field() -> None:
    candidate = _schema(_f("id", FieldType.LONG))
    report = check_compatibility(BASE, candidate, CompatibilityMode.FORWARD)
    assert not report.compatible
    assert any("name" in v for v in report.violations)


def test_full_requires_both_directions() -> None:
    # Adding an optional field satisfies both backward and forward.
    ok = _schema(
        _f("id", FieldType.LONG),
        _f("name", FieldType.STRING),
        _f("nickname", FieldType.STRING, nullable=True),
    )
    assert check_compatibility(BASE, ok, CompatibilityMode.FULL).compatible

    # Adding a required field passes forward but fails backward, so full fails.
    required = _schema(
        _f("id", FieldType.LONG),
        _f("name", FieldType.STRING),
        _f("nickname", FieldType.STRING),
    )
    assert not check_compatibility(BASE, required, CompatibilityMode.FULL).compatible


def test_nullability_narrowing_breaks_backward() -> None:
    nullable = _schema(_f("id", FieldType.LONG), _f("name", FieldType.STRING, nullable=True))
    non_null = _schema(_f("id", FieldType.LONG), _f("name", FieldType.STRING))
    report = check_compatibility(nullable, non_null, CompatibilityMode.BACKWARD)
    assert not report.compatible
