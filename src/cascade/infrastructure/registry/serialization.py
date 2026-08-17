from __future__ import annotations

import json
from typing import Any

from cascade.domain.contracts.value_objects import FieldType, SchemaDefinition, SchemaField

_AVRO_PRIMITIVES: dict[FieldType, Any] = {
    FieldType.BOOLEAN: "boolean",
    FieldType.INT: "int",
    FieldType.LONG: "long",
    FieldType.FLOAT: "float",
    FieldType.DOUBLE: "double",
    FieldType.STRING: "string",
    FieldType.BYTES: "bytes",
    FieldType.DATE: {"type": "int", "logicalType": "date"},
    FieldType.TIMESTAMP: {"type": "long", "logicalType": "timestamp-millis"},
}


def _field_type(field: SchemaField) -> Any:
    base = _AVRO_PRIMITIVES[field.type]
    if field.nullable:
        return ["null", base]
    return base


def _field_entry(field: SchemaField) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": field.name, "type": _field_type(field)}
    if field.doc:
        entry["doc"] = field.doc
    if field.nullable:
        entry["default"] = None
    return entry


def to_avro_schema(subject: str, schema: SchemaDefinition) -> dict[str, Any]:
    record_name = "".join(part.capitalize() for part in subject.replace("-", "_").split("_"))
    return {
        "type": "record",
        "name": record_name or "Record",
        "fields": [_field_entry(field) for field in schema.fields],
    }


def to_avro_json(subject: str, schema: SchemaDefinition) -> str:
    return json.dumps(to_avro_schema(subject, schema))
