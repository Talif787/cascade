from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cascade.application.common.errors import PermissionDeniedError
from cascade.infrastructure.config import Settings
from cascade.infrastructure.security.jwt import AuthenticationError, Principal, TokenVerifier

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> Principal:
    settings: Settings = request.app.state.settings
    verifier: TokenVerifier = request.app.state.token_verifier

    if not settings.auth_enabled:
        return verifier.verify("")

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("a bearer token is required")
    return verifier.verify(credentials.credentials)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_scopes(
    *required: str,
) -> Callable[[Principal], Coroutine[None, None, Principal]]:
    async def _guard(principal: CurrentPrincipal) -> Principal:
        missing = [scope for scope in required if not principal.has_scope(scope)]
        if missing:
            raise PermissionDeniedError(f"missing required scope(s): {', '.join(sorted(missing))}")
        return principal

    return _guard
