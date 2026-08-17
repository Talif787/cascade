from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cascade.domain.contracts.aggregate import DataContract
from cascade.domain.contracts.compatibility import CompatibilityReport
from cascade.domain.contracts.entities import SchemaVersion


@dataclass(frozen=True, slots=True)
class SchemaFieldView:
    name: str
    type: str
    nullable: bool
    has_default: bool
    doc: str


@dataclass(frozen=True, slots=True)
class SchemaVersionView:
    version: int
    status: str
    registry_id: int | None
    created_at: datetime
    fields: list[SchemaFieldView]

    @classmethod
    def from_entity(cls, entity: SchemaVersion) -> SchemaVersionView:
        return cls(
            version=entity.version,
            status=entity.status.value,
            registry_id=entity.registry_id,
            created_at=entity.created_at,
            fields=[
                SchemaFieldView(
                    name=f.name,
                    type=f.type.value,
                    nullable=f.nullable,
                    has_default=f.has_default,
                    doc=f.doc,
                )
                for f in entity.schema.fields
            ],
        )


@dataclass(frozen=True, slots=True)
class ContractView:
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
    schema_versions: list[SchemaVersionView]

    @classmethod
    def from_aggregate(cls, contract: DataContract) -> ContractView:
        return cls(
            id=str(contract.id),
            name=str(contract.name),
            schema_format=contract.schema_format.value,
            compatibility_mode=contract.compatibility_mode.value,
            status=contract.status.value,
            description=contract.description,
            latest_version=contract.latest_version.version,
            version=contract.version,
            created_at=contract.created_at,
            updated_at=contract.updated_at,
            schema_versions=[SchemaVersionView.from_entity(v) for v in contract.versions],
        )


@dataclass(frozen=True, slots=True)
class CompatibilityReportView:
    compatible: bool
    mode: str
    violations: list[str]

    @classmethod
    def from_report(cls, report: CompatibilityReport) -> CompatibilityReportView:
        return cls(
            compatible=report.compatible,
            mode=report.mode.value,
            violations=list(report.violations),
        )
