from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import AggregateRoot, utcnow
from cascade.domain.contracts.compatibility import CompatibilityReport, check_compatibility
from cascade.domain.contracts.entities import SchemaVersion
from cascade.domain.contracts.errors import (
    ContractAlreadyDeprecated,
    IncompatibleSchema,
    SchemaVersionNotFound,
)
from cascade.domain.contracts.events import (
    CompatibilityModeChanged,
    DataContractDeprecated,
    DataContractRegistered,
    SchemaVersionDeprecated,
    SchemaVersionPublished,
)
from cascade.domain.contracts.value_objects import (
    CompatibilityMode,
    ContractName,
    ContractStatus,
    DataContractId,
    SchemaDefinition,
    SchemaFormat,
)

_MAX_DESCRIPTION_LEN = 1024


class DataContract(AggregateRoot[DataContractId]):
    """A versioned schema contract governing the shape of a dataset."""

    def __init__(
        self,
        contract_id: DataContractId,
        *,
        name: ContractName,
        schema_format: SchemaFormat,
        compatibility_mode: CompatibilityMode,
        status: ContractStatus,
        description: str,
        versions: list[SchemaVersion],
        created_at: datetime,
        updated_at: datetime,
        version: int = 0,
    ) -> None:
        super().__init__(contract_id, version=version)
        self._name = name
        self._schema_format = schema_format
        self._compatibility_mode = compatibility_mode
        self._status = status
        self._description = description
        self._versions = versions
        self._created_at = created_at
        self._updated_at = updated_at

    @classmethod
    def register(
        cls,
        *,
        name: ContractName,
        schema_format: SchemaFormat,
        compatibility_mode: CompatibilityMode,
        initial_schema: SchemaDefinition,
        description: str = "",
    ) -> DataContract:
        now = utcnow()
        first = SchemaVersion.create(1, initial_schema)
        contract = cls(
            DataContractId.new(),
            name=name,
            schema_format=schema_format,
            compatibility_mode=compatibility_mode,
            status=ContractStatus.ACTIVE,
            description=description.strip()[:_MAX_DESCRIPTION_LEN],
            versions=[first],
            created_at=now,
            updated_at=now,
        )
        contract._record(DataContractRegistered(contract_id=contract.id, name=str(name)))
        contract._record(SchemaVersionPublished(contract_id=contract.id, version=1))
        return contract

    @property
    def name(self) -> ContractName:
        return self._name

    @property
    def schema_format(self) -> SchemaFormat:
        return self._schema_format

    @property
    def compatibility_mode(self) -> CompatibilityMode:
        return self._compatibility_mode

    @property
    def status(self) -> ContractStatus:
        return self._status

    @property
    def description(self) -> str:
        return self._description

    @property
    def versions(self) -> tuple[SchemaVersion, ...]:
        return tuple(self._versions)

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def latest_version(self) -> SchemaVersion:
        return self._versions[-1]

    def get_version(self, version: int) -> SchemaVersion:
        for candidate in self._versions:
            if candidate.version == version:
                return candidate
        raise SchemaVersionNotFound(version)

    def _latest_published(self) -> SchemaVersion | None:
        for candidate in reversed(self._versions):
            if candidate.is_published:
                return candidate
        return None

    def check_candidate(self, schema: SchemaDefinition) -> CompatibilityReport:
        baseline = self._latest_published()
        if baseline is None:
            return CompatibilityReport.ok(self._compatibility_mode)
        return check_compatibility(baseline.schema, schema, self._compatibility_mode)

    def publish_version(self, schema: SchemaDefinition) -> SchemaVersion:
        if self._status is ContractStatus.DEPRECATED:
            raise ContractAlreadyDeprecated()
        report = self.check_candidate(schema)
        if not report.compatible:
            raise IncompatibleSchema(report.mode.value, list(report.violations))
        new_version = SchemaVersion.create(self.latest_version.version + 1, schema)
        self._versions.append(new_version)
        self._touch()
        self._record(SchemaVersionPublished(contract_id=self.id, version=new_version.version))
        return new_version

    def change_compatibility_mode(self, mode: CompatibilityMode) -> None:
        if mode is self._compatibility_mode:
            return
        previous = self._compatibility_mode
        self._compatibility_mode = mode
        self._touch()
        self._record(CompatibilityModeChanged(contract_id=self.id, previous=previous, current=mode))

    def deprecate_version(self, version: int) -> None:
        target = self.get_version(version)
        target.deprecate()
        self._touch()
        self._record(SchemaVersionDeprecated(contract_id=self.id, version=version))

    def deprecate(self) -> None:
        if self._status is ContractStatus.DEPRECATED:
            return
        self._status = ContractStatus.DEPRECATED
        self._touch()
        self._record(DataContractDeprecated(contract_id=self.id))

    def _touch(self) -> None:
        self._updated_at = utcnow()
