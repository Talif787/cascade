from __future__ import annotations

import structlog

from cascade.application.common.dto import Page
from cascade.application.common.errors import (
    ConflictError,
    InputValidationError,
    NotFoundError,
    SchemaIncompatibleError,
)
from cascade.application.common.unit_of_work import UnitOfWork, UnitOfWorkFactory
from cascade.application.contracts.commands import (
    ChangeCompatibilityModeCommand,
    CheckCompatibilityCommand,
    DeprecateVersionCommand,
    PublishSchemaVersionCommand,
    RegisterContractCommand,
    SchemaInput,
)
from cascade.application.contracts.dto import (
    CompatibilityReportView,
    ContractView,
    SchemaVersionView,
)
from cascade.application.contracts.queries import (
    GetContractQuery,
    GetSchemaVersionQuery,
    ListContractsQuery,
)
from cascade.application.contracts.registry import SchemaRegistry
from cascade.domain.common.errors import DomainError, ValidationError
from cascade.domain.contracts.aggregate import DataContract
from cascade.domain.contracts.entities import SchemaVersion
from cascade.domain.contracts.errors import IncompatibleSchema, SchemaVersionNotFound
from cascade.domain.contracts.repository import (
    ContractSortField,
    DataContractQuery,
)
from cascade.domain.contracts.value_objects import (
    CompatibilityMode,
    ContractName,
    ContractStatus,
    DataContractId,
    FieldType,
    SchemaDefinition,
    SchemaField,
    SchemaFormat,
)

_logger = structlog.get_logger(__name__)

_MAX_PAGE_SIZE = 100


class DataContractApplicationService:
    """Coordinates data contract use cases and schema registry side effects."""

    def __init__(self, uow_factory: UnitOfWorkFactory, registry: SchemaRegistry) -> None:
        self._uow_factory = uow_factory
        self._registry = registry

    async def register_contract(self, command: RegisterContractCommand) -> ContractView:
        name = _build_name(command.name)
        schema_format = _parse_format(command.schema_format)
        mode = _parse_mode(command.compatibility_mode)
        schema = _build_schema(command.schema)

        async with self._uow_factory() as uow:
            if await uow.contracts.exists_by_name(name):
                raise ConflictError(f"contract name {name!s} is already in use")
            contract = DataContract.register(
                name=name,
                schema_format=schema_format,
                compatibility_mode=mode,
                initial_schema=schema,
                description=command.description,
            )
            await self._register_with_registry(contract, contract.latest_version)
            await uow.contracts.add(contract)
            await uow.commit()
            _emit_events(contract)
            return ContractView.from_aggregate(contract)

    async def publish_version(self, command: PublishSchemaVersionCommand) -> SchemaVersionView:
        schema = _build_schema(command.schema)
        identity = DataContractId.from_string(command.contract_id)
        async with self._uow_factory() as uow:
            contract = await self._load(uow, identity, command.contract_id)
            try:
                version = contract.publish_version(schema)
            except IncompatibleSchema as exc:
                raise SchemaIncompatibleError(exc.mode, exc.violations) from exc
            except DomainError as exc:
                raise ConflictError(str(exc)) from exc
            await self._register_with_registry(contract, version)
            await uow.contracts.update(contract)
            await uow.commit()
            _emit_events(contract)
            return SchemaVersionView.from_entity(version)

    async def check_compatibility(
        self, command: CheckCompatibilityCommand
    ) -> CompatibilityReportView:
        schema = _build_schema(command.schema)
        identity = DataContractId.from_string(command.contract_id)
        async with self._uow_factory() as uow:
            contract = await self._load(uow, identity, command.contract_id)
            report = contract.check_candidate(schema)
            return CompatibilityReportView.from_report(report)

    async def change_compatibility_mode(
        self, command: ChangeCompatibilityModeCommand
    ) -> ContractView:
        mode = _parse_mode(command.compatibility_mode)
        identity = DataContractId.from_string(command.contract_id)
        async with self._uow_factory() as uow:
            contract = await self._load(uow, identity, command.contract_id)
            contract.change_compatibility_mode(mode)
            await uow.contracts.update(contract)
            await uow.commit()
            _emit_events(contract)
            return ContractView.from_aggregate(contract)

    async def deprecate_version(self, command: DeprecateVersionCommand) -> ContractView:
        identity = DataContractId.from_string(command.contract_id)
        async with self._uow_factory() as uow:
            contract = await self._load(uow, identity, command.contract_id)
            try:
                contract.deprecate_version(command.version)
            except SchemaVersionNotFound as exc:
                raise NotFoundError("schema version", str(command.version)) from exc
            await uow.contracts.update(contract)
            await uow.commit()
            _emit_events(contract)
            return ContractView.from_aggregate(contract)

    async def deprecate_contract(self, contract_id: str) -> ContractView:
        identity = DataContractId.from_string(contract_id)
        async with self._uow_factory() as uow:
            contract = await self._load(uow, identity, contract_id)
            contract.deprecate()
            await uow.contracts.update(contract)
            await uow.commit()
            _emit_events(contract)
            return ContractView.from_aggregate(contract)

    async def get_contract(self, query: GetContractQuery) -> ContractView:
        identity = DataContractId.from_string(query.contract_id)
        async with self._uow_factory() as uow:
            contract = await self._load(uow, identity, query.contract_id)
            return ContractView.from_aggregate(contract)

    async def get_version(self, query: GetSchemaVersionQuery) -> SchemaVersionView:
        identity = DataContractId.from_string(query.contract_id)
        async with self._uow_factory() as uow:
            contract = await self._load(uow, identity, query.contract_id)
            try:
                version = contract.get_version(query.version)
            except SchemaVersionNotFound as exc:
                raise NotFoundError("schema version", str(query.version)) from exc
            return SchemaVersionView.from_entity(version)

    async def list_contracts(self, query: ListContractsQuery) -> Page[ContractView]:
        size = _bounded_size(query.size)
        page = max(query.page, 1)
        repo_query = DataContractQuery(
            status=_parse_status(query.status),
            offset=(page - 1) * size,
            limit=size,
            sort_by=_parse_sort_field(query.sort_by),
            descending=query.descending,
        )
        async with self._uow_factory() as uow:
            contracts, total = await uow.contracts.list(repo_query)
            return Page(
                items=[ContractView.from_aggregate(c) for c in contracts],
                total=total,
                page=page,
                size=size,
            )

    async def _register_with_registry(self, contract: DataContract, version: SchemaVersion) -> None:
        result = await self._registry.register(
            subject=str(contract.name),
            schema=version.schema,
            schema_format=contract.schema_format,
        )
        version.assign_registry_id(result.registry_id)

    async def _load(self, uow: UnitOfWork, identity: DataContractId, raw_id: str) -> DataContract:
        contract = await uow.contracts.get(identity)
        if contract is None:
            raise NotFoundError("contract", raw_id)
        return contract


def _build_name(raw: str) -> ContractName:
    try:
        return ContractName(raw)
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _build_schema(payload: SchemaInput) -> SchemaDefinition:
    try:
        fields = tuple(
            SchemaField(
                name=f.name,
                type=FieldType(f.type),
                nullable=f.nullable,
                has_default=f.has_default,
                doc=f.doc,
            )
            for f in payload.fields
        )
        return SchemaDefinition(fields=fields)
    except ValueError as exc:
        raise InputValidationError(f"unsupported field type: {exc}") from exc
    except ValidationError as exc:
        raise InputValidationError(str(exc)) from exc


def _parse_format(raw: str) -> SchemaFormat:
    try:
        return SchemaFormat(raw)
    except ValueError as exc:
        raise InputValidationError(f"unsupported schema format {raw!r}") from exc


def _parse_mode(raw: str) -> CompatibilityMode:
    try:
        return CompatibilityMode(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown compatibility mode {raw!r}") from exc


def _parse_status(raw: str | None) -> ContractStatus | None:
    if raw is None:
        return None
    try:
        return ContractStatus(raw)
    except ValueError as exc:
        raise InputValidationError(f"unknown contract status {raw!r}") from exc


def _parse_sort_field(raw: str) -> ContractSortField:
    try:
        return ContractSortField(raw)
    except ValueError as exc:
        raise InputValidationError(f"cannot sort by {raw!r}") from exc


def _bounded_size(size: int) -> int:
    if size < 1:
        return 1
    return min(size, _MAX_PAGE_SIZE)


def _emit_events(contract: DataContract) -> None:
    for event in contract.pull_events():
        _logger.info(
            "domain_event",
            event_type=event.event_type,
            contract_id=str(contract.id),
            occurred_at=event.occurred_at.isoformat(),
        )
