from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from cascade.application.common.errors import (
    ConcurrencyError,
    ConflictError,
    InputValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from cascade.domain.common.errors import DomainError
from cascade.infrastructure.security.jwt import AuthenticationError
from cascade.presentation.api.middleware.correlation import get_correlation_id

_logger = structlog.get_logger(__name__)
_PROBLEM_MEDIA_TYPE = "application/problem+json"


def _problem(status: int, title: str, detail: str, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type=_PROBLEM_MEDIA_TYPE,
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": request.url.path,
            "correlation_id": get_correlation_id() or None,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return _problem(404, "Not Found", str(exc), request)

    @app.exception_handler(ConflictError)
    async def _conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return _problem(409, "Conflict", str(exc), request)

    @app.exception_handler(ConcurrencyError)
    async def _concurrency(request: Request, exc: ConcurrencyError) -> JSONResponse:
        return _problem(409, "Conflict", str(exc), request)

    @app.exception_handler(InputValidationError)
    async def _input_validation(request: Request, exc: InputValidationError) -> JSONResponse:
        return _problem(422, "Unprocessable Entity", str(exc), request)

    @app.exception_handler(AuthenticationError)
    async def _auth(request: Request, exc: AuthenticationError) -> JSONResponse:
        return _problem(401, "Unauthorized", str(exc), request)

    @app.exception_handler(PermissionDeniedError)
    async def _forbidden(request: Request, exc: PermissionDeniedError) -> JSONResponse:
        return _problem(403, "Forbidden", str(exc), request)

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return _problem(422, "Unprocessable Entity", str(exc), request)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
            for error in exc.errors()
        )
        return _problem(422, "Unprocessable Entity", detail or "invalid request", request)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        _logger.error("unhandled_exception", error=str(exc), path=request.url.path, exc_info=exc)
        return _problem(500, "Internal Server Error", "an unexpected error occurred", request)
