from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from types import TracebackType

from cascade.domain.contracts.repository import DataContractRepository
from cascade.domain.pipelines.repository import PipelineRepository


class UnitOfWork(ABC):
    """Transactional boundary exposing the aggregate repositories."""

    pipelines: PipelineRepository
    contracts: DataContractRepository

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        await self.close()

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
