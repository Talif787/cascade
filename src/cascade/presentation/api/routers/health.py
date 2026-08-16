from __future__ import annotations

import structlog
from fastapi import APIRouter, Request, Response, status

from cascade.presentation.api.schemas.common import HealthResponse

router = APIRouter(tags=["health"])
_logger = structlog.get_logger("cascade.health")


@router.get("/livez", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse)
async def readiness(request: Request, response: Response) -> HealthResponse:
    checks: dict[str, str] = {}
    healthy = True
    for name, probe in request.app.state.health_checks.items():
        try:
            ok = await probe()
        except Exception as exc:
            ok = False
            _logger.warning("readiness_probe_failed", check=name, error=str(exc))
        checks[name] = "ok" if ok else "unavailable"
        healthy = healthy and ok

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", checks=checks)
