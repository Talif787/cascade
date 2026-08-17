from __future__ import annotations

import pytest

from cascade.sdk.validator import (
    RecordValidationError,
    ResolvedSchema,
    SchemaFieldSpec,
)


def _schema(*fields: SchemaFieldSpec) -> ResolvedSchema:
    return ResolvedSchema(
        contract_id="c-1",
        contract_name="orders-value",
        version=1,
        registry_id=7,
        fields=fields,
    )


def test_valid_record_passes() -> None:
    schema = _schema(
        SchemaFieldSpec(name="id", type="long"),
        SchemaFieldSpec(name="amount", type="double"),
        SchemaFieldSpec(name="currency", type="string", nullable=True),
    )
    schema.validate_record({"id": 1, "amount": 9.5, "currency": None})


def test_missing_required_field_is_reported() -> None:
    schema = _schema(SchemaFieldSpec(name="id", type="long"))
    with pytest.raises(RecordValidationError) as exc:
        schema.validate_record({})
    assert "missing required field 'id'" in exc.value.violations[0]


def test_default_field_may_be_omitted() -> None:
    schema = _schema(
        SchemaFieldSpec(name="id", type="long"),
        SchemaFieldSpec(name="region", type="string", has_default=True),
    )
    schema.validate_record({"id": 1})


def test_type_mismatch_is_reported() -> None:
    schema = _schema(SchemaFieldSpec(name="id", type="long"))
    violations = schema.check_record({"id": "nope"})
    assert violations and "expected long" in violations[0]


def test_boolean_is_not_an_integer() -> None:
    schema = _schema(SchemaFieldSpec(name="count", type="long"))
    violations = schema.check_record({"count": True})
    assert violations


def test_unexpected_field_is_reported() -> None:
    schema = _schema(SchemaFieldSpec(name="id", type="long"))
    violations = schema.check_record({"id": 1, "extra": "x"})
    assert any("unexpected field 'extra'" in v for v in violations)


def test_timestamp_accepts_int_or_iso_string() -> None:
    schema = _schema(SchemaFieldSpec(name="ts", type="timestamp"))
    schema.validate_record({"ts": 1719878400})
    schema.validate_record({"ts": "2026-03-01T00:00:00Z"})


def test_null_on_non_nullable_is_reported() -> None:
    schema = _schema(SchemaFieldSpec(name="id", type="long"))
    violations = schema.check_record({"id": None})
    assert any("must not be null" in v for v in violations)
