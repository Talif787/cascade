from __future__ import annotations

import json
import time

from redis.asyncio import Redis

from cascade.infrastructure.cache.base import Cache, IdempotentResponse, RateLimitDecision

_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
local delta = math.max(0, now - ts) / 1000.0
tokens = math.min(capacity, tokens + delta * rate)
local allowed = 0
local retry_after = 0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
else
  retry_after = math.ceil((requested - tokens) / rate)
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', key, math.ceil(capacity / rate * 1000) + 1000)
return {allowed, retry_after}
"""


class RedisCache(Cache):
    def __init__(self, client: Redis) -> None:
        self._client = client
        self._token_bucket = client.register_script(_TOKEN_BUCKET_SCRIPT)

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def get_idempotent(self, key: str) -> IdempotentResponse | None:
        raw = await self._client.get(self._idempotency_key(key))
        if raw is None:
            return None
        payload = json.loads(raw)
        return IdempotentResponse(status_code=payload["status_code"], body=payload["body"])

    async def store_idempotent(
        self, key: str, response: IdempotentResponse, ttl_seconds: int
    ) -> None:
        payload = json.dumps({"status_code": response.status_code, "body": response.body})
        await self._client.set(self._idempotency_key(key), payload, ex=ttl_seconds, nx=True)

    async def check_rate_limit(
        self, identity: str, *, rate_per_second: float, burst: int
    ) -> RateLimitDecision:
        now_ms = int(time.time() * 1000)
        allowed, retry_after = await self._token_bucket(
            keys=[f"ratelimit:{identity}"],
            args=[rate_per_second, burst, now_ms, 1],
        )
        return RateLimitDecision(allowed=bool(allowed), retry_after_seconds=int(retry_after))

    @staticmethod
    def _idempotency_key(key: str) -> str:
        return f"idempotency:{key}"
