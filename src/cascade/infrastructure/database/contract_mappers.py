from __future__ import annotations

from typing import Any

from cascade.domain.contracts.aggregate import DataContract
from cascade.domain.contracts.entities import SchemaVersion
from cascade.domain.contracts.value_objects import (
    CompatibilityMode,
    ContractName,
    ContractStatus,
    DataContractId,
    FieldType,
    SchemaDefinition,
    SchemaField,
    SchemaFormat,
    VersionStatus,
)
from cascade.infrastructure.database.models import DataContractModel, SchemaVersionModel


def _field_to_dict(field: SchemaField) -> dict[str, Any]:
    return {
        "name": field.name,
        "type": field.type.value,
        "nullable": field.nullable,
        "has_default": field.has_default,
        "doc": field.doc,
    }


def schema_to_dict(schema: SchemaDefinition) -> dict[str, Any]:
    return {"fields": [_field_to_dict(field) for field in schema.fields]}


def dict_to_schema(payload: dict[str, Any]) -> SchemaDefinition:
    fields = tuple(
        SchemaField(
            name=raw["name"],
            type=FieldType(raw["type"]),
            nullable=raw.get("nullable", False),
            has_default=raw.get("has_default", False),
            doc=raw.get("doc", ""),
        )
        for raw in payload["fields"]
    )
    return SchemaDefinition(fields=fields)


def version_to_model(contract_id: object, version: SchemaVersion) -> SchemaVersionModel:
    return SchemaVersionModel(
        contract_id=contract_id,
        version=version.version,
        definition=schema_to_dict(version.schema),
        status=version.status.value,
        registry_id=version.registry_id,
        created_at=version.created_at,
    )


def model_to_version(model: SchemaVersionModel) -> SchemaVersion:
    return SchemaVersion(
        version=model.version,
        schema=dict_to_schema(model.definition),
        status=VersionStatus(model.status),
        created_at=model.created_at,
        registry_id=model.registry_id,
    )


def contract_to_model(contract: DataContract) -> DataContractModel:
    model = DataContractModel(
        id=contract.id.value,
        name=str(contract.name),
        schema_format=contract.schema_format.value,
        compatibility_mode=contract.compatibility_mode.value,
        status=contract.status.value,
        description=contract.description,
        version=contract.version,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
    )
    model.schema_versions = [
        version_to_model(contract.id.value, version) for version in contract.versions
    ]
    return model


def model_to_contract(model: DataContractModel) -> DataContract:
    versions = [model_to_version(version) for version in model.schema_versions]
    return DataContract(
        DataContractId(model.id),
        name=ContractName(model.name),
        schema_format=SchemaFormat(model.schema_format),
        compatibility_mode=CompatibilityMode(model.compatibility_mode),
        status=ContractStatus(model.status),
        description=model.description,
        versions=versions,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )
