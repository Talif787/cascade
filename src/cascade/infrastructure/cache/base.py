from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


@dataclass(frozen=True, slots=True)
class IdempotentResponse:
    status_code: int
    body: str


class Cache(ABC):
    """Port for caching, idempotency storage, and distributed rate limiting."""

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def get_idempotent(self, key: str) -> IdempotentResponse | None: ...

    @abstractmethod
    async def store_idempotent(
        self, key: str, response: IdempotentResponse, ttl_seconds: int
    ) -> None: ...

    @abstractmethod
    async def check_rate_limit(
        self, identity: str, *, rate_per_second: float, burst: int
    ) -> RateLimitDecision: ...
