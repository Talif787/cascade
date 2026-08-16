from __future__ import annotations

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from cascade.infrastructure.metrics import REQUEST_COUNT, REQUEST_LATENCY

_logger = structlog.get_logger("cascade.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            route_template = _route_template(request)
            REQUEST_LATENCY.labels(request.method, route_template).observe(duration)
            REQUEST_COUNT.labels(request.method, route_template, str(status_code)).inc()
            _logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                route=route_template,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
                client=request.client.host if request.client else None,
            )


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)
