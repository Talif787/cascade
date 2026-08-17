from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cascade.application.common.unit_of_work import UnitOfWork
from cascade.infrastructure.repositories.contract_repository import (
    SqlAlchemyDataContractRepository,
)
from cascade.infrastructure.repositories.dataset_repository import (
    SqlAlchemyDatasetRepository,
)
from cascade.infrastructure.repositories.ingestion_repository import (
    SqlAlchemyIngestionSourceRepository,
)
from cascade.infrastructure.repositories.pipeline_repository import SqlAlchemyPipelineRepository
from cascade.infrastructure.repositories.serving_view_repository import (
    SqlAlchemyServingViewRepository,
)
from cascade.infrastructure.repositories.stream_job_repository import (
    SqlAlchemyStreamJobRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self.pipelines = SqlAlchemyPipelineRepository(self._session)
        self.contracts = SqlAlchemyDataContractRepository(self._session)
        self.ingestion_sources = SqlAlchemyIngestionSourceRepository(self._session)
        self.stream_jobs = SqlAlchemyStreamJobRepository(self._session)
        self.datasets = SqlAlchemyDatasetRepository(self._session)
        self.serving_views = SqlAlchemyServingViewRepository(self._session)
        return self

    async def commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
