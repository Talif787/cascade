from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cascade.application.common.errors import ConcurrencyError, ConflictError
from cascade.domain.contracts.aggregate import DataContract
from cascade.domain.contracts.repository import (
    ContractSortField,
    DataContractQuery,
    DataContractRepository,
)
from cascade.domain.contracts.value_objects import ContractName, DataContractId
from cascade.infrastructure.database.contract_mappers import (
    contract_to_model,
    model_to_contract,
    version_to_model,
)
from cascade.infrastructure.database.models import DataContractModel

_SORT_COLUMNS = {
    ContractSortField.NAME: DataContractModel.name,
    ContractSortField.STATUS: DataContractModel.status,
    ContractSortField.CREATED_AT: DataContractModel.created_at,
    ContractSortField.UPDATED_AT: DataContractModel.updated_at,
}


class SqlAlchemyDataContractRepository(DataContractRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, contract: DataContract) -> None:
        self._session.add(contract_to_model(contract))
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"contract name {contract.name!s} is already in use") from exc

    async def update(self, contract: DataContract) -> None:
        model = await self._session.get(DataContractModel, contract.id.value)
        if model is None or model.version != contract.version:
            raise ConcurrencyError(f"contract {contract.id!s} was modified concurrently")

        model.compatibility_mode = contract.compatibility_mode.value
        model.status = contract.status.value
        model.description = contract.description
        model.updated_at = contract.updated_at
        model.version = contract.version + 1

        existing = {row.version: row for row in model.schema_versions}
        for domain_version in contract.versions:
            row = existing.get(domain_version.version)
            if row is None:
                model.schema_versions.append(version_to_model(contract.id.value, domain_version))
            else:
                row.status = domain_version.status.value
                row.registry_id = domain_version.registry_id

        await self._session.flush()
        contract._version = model.version

    async def get(self, contract_id: DataContractId) -> DataContract | None:
        model = await self._session.get(DataContractModel, contract_id.value)
        return model_to_contract(model) if model is not None else None

    async def get_by_name(self, name: ContractName) -> DataContract | None:
        result = await self._session.execute(
            select(DataContractModel).where(DataContractModel.name == str(name))
        )
        model = result.scalar_one_or_none()
        return model_to_contract(model) if model is not None else None

    async def exists_by_name(self, name: ContractName) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(DataContractModel)
            .where(DataContractModel.name == str(name))
        )
        return bool(result.scalar_one())

    async def list(self, query: DataContractQuery) -> tuple[list[DataContract], int]:
        base = select(DataContractModel)
        if query.status is not None:
            base = base.where(DataContractModel.status == query.status.value)

        total_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(total_result.scalar_one())

        column = _SORT_COLUMNS[query.sort_by]
        order = column.desc() if query.descending else column.asc()
        page_result = await self._session.execute(
            base.order_by(order).offset(query.offset).limit(query.limit)
        )
        models = page_result.scalars().unique().all()
        return [model_to_contract(model) for model in models], total
