from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class FieldInput:
    name: str
    type: str
    nullable: bool = False
    has_default: bool = False
    doc: str = ""


@dataclass(frozen=True, slots=True)
class SchemaInput:
    fields: list[FieldInput] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RegisterContractCommand:
    name: str
    schema_format: str
    compatibility_mode: str
    schema: SchemaInput
    description: str = ""


@dataclass(frozen=True, slots=True)
class PublishSchemaVersionCommand:
    contract_id: str
    schema: SchemaInput


@dataclass(frozen=True, slots=True)
class CheckCompatibilityCommand:
    contract_id: str
    schema: SchemaInput


@dataclass(frozen=True, slots=True)
class ChangeCompatibilityModeCommand:
    contract_id: str
    compatibility_mode: str


@dataclass(frozen=True, slots=True)
class DeprecateVersionCommand:
    contract_id: str
    version: int
