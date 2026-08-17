from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from cascade.application.contracts.dto import (
    CompatibilityReportView,
    ContractView,
    SchemaVersionView,
)


class SchemaFieldPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128, examples=["order_id"])
    type: str = Field(examples=["string"])
    nullable: bool = False
    has_default: bool = False
    doc: str = Field(default="", max_length=512)


class SchemaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[SchemaFieldPayload] = Field(min_length=1)


class RegisterContractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=63, examples=["orders-value"])
    schema_format: str = Field(default="avro", examples=["avro"])
    compatibility_mode: str = Field(default="backward", examples=["backward"])
    schema_definition: SchemaPayload = Field(alias="schema")
    description: str = Field(default="", max_length=1024)


class PublishVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_definition: SchemaPayload = Field(alias="schema")


class CheckCompatibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_definition: SchemaPayload = Field(alias="schema")


class ChangeCompatibilityModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compatibility_mode: str = Field(examples=["full"])


class SchemaFieldResponse(BaseModel):
    name: str
    type: str
    nullable: bool
    has_default: bool
    doc: str


class SchemaVersionResponse(BaseModel):
    version: int
    status: str
    registry_id: int | None
    created_at: datetime
    fields: list[SchemaFieldResponse]

    @classmethod
    def from_view(cls, view: SchemaVersionView) -> SchemaVersionResponse:
        return cls(
            version=view.version,
            status=view.status,
            registry_id=view.registry_id,
            created_at=view.created_at,
            fields=[
                SchemaFieldResponse(
                    name=f.name,
                    type=f.type,
                    nullable=f.nullable,
                    has_default=f.has_default,
                    doc=f.doc,
                )
                for f in view.fields
            ],
        )


class ContractResponse(BaseModel):
    id: str
    name: str
    schema_format: str
    compatibility_mode: str
    status: str
    description: str
    latest_version: int
    version: int
    created_at: datetime
    updated_at: datetime
    schema_versions: list[SchemaVersionResponse]

    @classmethod
    def from_view(cls, view: ContractView) -> ContractResponse:
        return cls(
            id=view.id,
            name=view.name,
            schema_format=view.schema_format,
            compatibility_mode=view.compatibility_mode,
            status=view.status,
            description=view.description,
            latest_version=view.latest_version,
            version=view.version,
            created_at=view.created_at,
            updated_at=view.updated_at,
            schema_versions=[SchemaVersionResponse.from_view(v) for v in view.schema_versions],
        )


class CompatibilityReportResponse(BaseModel):
    compatible: bool
    mode: str
    violations: list[str]

    @classmethod
    def from_view(cls, view: CompatibilityReportView) -> CompatibilityReportResponse:
        return cls(compatible=view.compatible, mode=view.mode, violations=view.violations)
