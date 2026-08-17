from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from cascade.domain.contracts.errors import (
    InvalidContractId,
    InvalidContractName,
    InvalidSchemaDefinition,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class DataContractId:
    value: uuid.UUID

    @staticmethod
    def new() -> DataContractId:
        return DataContractId(uuid.uuid4())

    @staticmethod
    def from_string(raw: str) -> DataContractId:
        try:
            return DataContractId(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidContractId(str(raw)) from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class ContractName:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _NAME_PATTERN.match(self.value):
            raise InvalidContractName(str(self.value))

    def __str__(self) -> str:
        return self.value


class SchemaFormat(StrEnum):
    AVRO = "avro"
    PROTOBUF = "protobuf"
    JSON_SCHEMA = "json_schema"


class CompatibilityMode(StrEnum):
    NONE = "none"
    BACKWARD = "backward"
    FORWARD = "forward"
    FULL = "full"


class ContractStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class VersionStatus(StrEnum):
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class FieldType(StrEnum):
    BOOLEAN = "boolean"
    INT = "int"
    LONG = "long"
    FLOAT = "float"
    DOUBLE = "double"
    STRING = "string"
    BYTES = "bytes"
    DATE = "date"
    TIMESTAMP = "timestamp"


# Widening promotions: a value written as the key type can be read as any of the
# value types. Used by the compatibility engine and modeled on Avro's rules.
_PROMOTIONS: dict[FieldType, frozenset[FieldType]] = {
    FieldType.INT: frozenset({FieldType.LONG, FieldType.FLOAT, FieldType.DOUBLE}),
    FieldType.LONG: frozenset({FieldType.FLOAT, FieldType.DOUBLE}),
    FieldType.FLOAT: frozenset({FieldType.DOUBLE}),
    FieldType.STRING: frozenset({FieldType.BYTES}),
    FieldType.BYTES: frozenset({FieldType.STRING}),
    FieldType.DATE: frozenset({FieldType.TIMESTAMP}),
}


def is_promotable(source: FieldType, target: FieldType) -> bool:
    return source == target or target in _PROMOTIONS.get(source, frozenset())


@dataclass(frozen=True, slots=True)
class SchemaField:
    name: str
    type: FieldType
    nullable: bool = False
    has_default: bool = False
    doc: str = ""

    def __post_init__(self) -> None:
        if not _FIELD_NAME_PATTERN.match(self.name):
            raise InvalidSchemaDefinition(f"invalid field name {self.name!r}")

    @property
    def has_effective_default(self) -> bool:
        return self.has_default or self.nullable


@dataclass(frozen=True, slots=True)
class SchemaDefinition:
    fields: tuple[SchemaField, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.fields:
            raise InvalidSchemaDefinition("a schema must declare at least one field")
        names = [f.name for f in self.fields]
        if len(names) != len(set(names)):
            raise InvalidSchemaDefinition("field names must be unique within a schema")

    def field_map(self) -> dict[str, SchemaField]:
        return {f.name: f for f in self.fields}
