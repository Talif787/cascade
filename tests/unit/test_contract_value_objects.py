from __future__ import annotations

import pytest

from cascade.domain.contracts.errors import (
    InvalidContractId,
    InvalidContractName,
    InvalidSchemaDefinition,
)
from cascade.domain.contracts.value_objects import (
    ContractName,
    DataContractId,
    FieldType,
    SchemaDefinition,
    SchemaField,
    is_promotable,
)


def test_contract_name_accepts_valid_slug() -> None:
    assert str(ContractName("orders-value")) == "orders-value"


@pytest.mark.parametrize("value", ["Ab", "1orders", "has space", "UPPER", "x"])
def test_contract_name_rejects_invalid(value: str) -> None:
    with pytest.raises(InvalidContractName):
        ContractName(value)


def test_contract_id_round_trip() -> None:
    identity = DataContractId.new()
    assert DataContractId.from_string(str(identity)) == identity


def test_contract_id_rejects_garbage() -> None:
    with pytest.raises(InvalidContractId):
        DataContractId.from_string("not-a-uuid")


def test_schema_requires_fields() -> None:
    with pytest.raises(InvalidSchemaDefinition):
        SchemaDefinition(fields=())


def test_schema_rejects_duplicate_field_names() -> None:
    with pytest.raises(InvalidSchemaDefinition):
        SchemaDefinition(
            fields=(
                SchemaField(name="id", type=FieldType.LONG),
                SchemaField(name="id", type=FieldType.STRING),
            )
        )


def test_field_effective_default_from_nullable() -> None:
    field = SchemaField(name="note", type=FieldType.STRING, nullable=True)
    assert field.has_effective_default


@pytest.mark.parametrize(
    ("source", "target", "expected"),
    [
        (FieldType.INT, FieldType.LONG, True),
        (FieldType.INT, FieldType.DOUBLE, True),
        (FieldType.LONG, FieldType.INT, False),
        (FieldType.STRING, FieldType.BYTES, True),
        (FieldType.DOUBLE, FieldType.FLOAT, False),
        (FieldType.DATE, FieldType.TIMESTAMP, True),
    ],
)
def test_promotions(source: FieldType, target: FieldType, expected: bool) -> None:
    assert is_promotable(source, target) is expected
