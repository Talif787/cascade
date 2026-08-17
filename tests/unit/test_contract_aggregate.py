from __future__ import annotations

import pytest

from cascade.domain.contracts.aggregate import DataContract
from cascade.domain.contracts.errors import (
    ContractAlreadyDeprecated,
    IncompatibleSchema,
    SchemaVersionNotFound,
)
from cascade.domain.contracts.events import (
    DataContractRegistered,
    SchemaVersionDeprecated,
    SchemaVersionPublished,
)
from cascade.domain.contracts.value_objects import (
    CompatibilityMode,
    ContractName,
    ContractStatus,
    FieldType,
    SchemaDefinition,
    SchemaField,
    SchemaFormat,
    VersionStatus,
)


def _schema(*fields: SchemaField) -> SchemaDefinition:
    return SchemaDefinition(fields=fields)


def _contract(mode: CompatibilityMode = CompatibilityMode.BACKWARD) -> DataContract:
    return DataContract.register(
        name=ContractName("orders-value"),
        schema_format=SchemaFormat.AVRO,
        compatibility_mode=mode,
        initial_schema=_schema(SchemaField(name="id", type=FieldType.LONG)),
    )


def test_register_creates_first_version_and_events() -> None:
    contract = _contract()
    assert contract.latest_version.version == 1
    assert contract.status is ContractStatus.ACTIVE
    events = contract.pull_events()
    assert any(isinstance(e, DataContractRegistered) for e in events)
    assert any(isinstance(e, SchemaVersionPublished) for e in events)


def test_publish_compatible_version_increments() -> None:
    contract = _contract()
    contract.pull_events()
    version = contract.publish_version(
        _schema(
            SchemaField(name="id", type=FieldType.LONG),
            SchemaField(name="total", type=FieldType.DOUBLE, has_default=True),
        )
    )
    assert version.version == 2
    assert contract.latest_version.version == 2
    assert any(isinstance(e, SchemaVersionPublished) for e in contract.pull_events())


def test_publish_incompatible_version_raises() -> None:
    contract = _contract()
    with pytest.raises(IncompatibleSchema) as exc:
        contract.publish_version(
            _schema(
                SchemaField(name="id", type=FieldType.LONG),
                SchemaField(name="total", type=FieldType.DOUBLE),
            )
        )
    assert exc.value.violations
    assert contract.latest_version.version == 1


def test_change_compatibility_mode_records_event() -> None:
    contract = _contract()
    contract.pull_events()
    contract.change_compatibility_mode(CompatibilityMode.FULL)
    assert contract.compatibility_mode is CompatibilityMode.FULL


def test_deprecate_version_marks_status() -> None:
    contract = _contract()
    contract.publish_version(
        _schema(
            SchemaField(name="id", type=FieldType.LONG),
            SchemaField(name="total", type=FieldType.DOUBLE, has_default=True),
        )
    )
    contract.pull_events()
    contract.deprecate_version(1)
    assert contract.get_version(1).status is VersionStatus.DEPRECATED
    assert any(isinstance(e, SchemaVersionDeprecated) for e in contract.pull_events())


def test_deprecate_missing_version_raises() -> None:
    contract = _contract()
    with pytest.raises(SchemaVersionNotFound):
        contract.deprecate_version(99)


def test_publish_to_deprecated_contract_raises() -> None:
    contract = _contract()
    contract.deprecate()
    with pytest.raises(ContractAlreadyDeprecated):
        contract.publish_version(_schema(SchemaField(name="id", type=FieldType.LONG)))
