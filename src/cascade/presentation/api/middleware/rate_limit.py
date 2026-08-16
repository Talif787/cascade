from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from cascade.infrastructure.cache.base import Cache
from cascade.presentation.api.middleware.correlation import get_correlation_id

_EXEMPT_PREFIXES = ("/livez", "/readyz", "/healthz", "/metrics", "/docs", "/openapi.json", "/redoc")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, *, rate_per_second: float, burst: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._rate_per_second = rate_per_second
        self._burst = burst

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if any(request.url.path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)

        cache: Cache = request.app.state.cache
        identity = _client_identity(request)
        decision = await cache.check_rate_limit(
            identity, rate_per_second=self._rate_per_second, burst=self._burst
        )
        if not decision.allowed:
            return _too_many_requests(decision.retry_after_seconds)
        return await call_next(request)


def _client_identity(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _too_many_requests(retry_after: int) -> Response:
    payload = {
        "type": "about:blank",
        "title": "Too Many Requests",
        "status": 429,
        "detail": "rate limit exceeded",
        "correlation_id": get_correlation_id() or None,
    }
    return Response(
        content=json.dumps(payload),
        status_code=429,
        media_type="application/problem+json",
        headers={"Retry-After": str(max(retry_after, 1))},
    )
