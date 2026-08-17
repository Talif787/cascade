from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import jwt
from jwt import InvalidTokenError, PyJWKClient

from cascade.infrastructure.config import Settings


class AuthenticationError(Exception):
    """Raised when a bearer token cannot be verified."""


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    roles: frozenset[str] = field(default_factory=frozenset)
    claims: dict[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


class TokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str) -> Principal: ...


def _principal_from_claims(claims: dict[str, Any]) -> Principal:
    subject = claims.get("sub")
    if not subject:
        raise AuthenticationError("token is missing a subject claim")
    raw_scope = claims.get("scope", "")
    scopes = frozenset(raw_scope.split()) if isinstance(raw_scope, str) else frozenset(raw_scope)
    roles = frozenset(claims.get("roles", []))
    return Principal(subject=subject, scopes=scopes, roles=roles, claims=claims)


class HS256TokenVerifier(TokenVerifier):
    def __init__(self, secret: str, issuer: str | None, audience: str | None) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "sub"], "verify_aud": self._audience is not None},
            )
        except InvalidTokenError as exc:
            raise AuthenticationError(str(exc)) from exc
        return _principal_from_claims(claims)


class JwksTokenVerifier(TokenVerifier):
    def __init__(
        self, jwks_url: str, algorithm: str, issuer: str | None, audience: str | None
    ) -> None:
        self._client = PyJWKClient(jwks_url)
        self._algorithm = algorithm
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> Principal:
        try:
            signing_key = self._client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "sub"], "verify_aud": self._audience is not None},
            )
        except InvalidTokenError as exc:
            raise AuthenticationError(str(exc)) from exc
        return _principal_from_claims(claims)


class AllowAllTokenVerifier(TokenVerifier):
    """Used only when authentication is explicitly disabled for local development."""

    def verify(self, token: str) -> Principal:
        return Principal(
            subject="anonymous",
            scopes=frozenset(
                {
                    "pipelines:read",
                    "pipelines:write",
                    "contracts:read",
                    "contracts:write",
                    "ingestion:read",
                    "ingestion:write",
                    "processing:read",
                    "processing:write",
                    "lakehouse:read",
                    "lakehouse:write",
                    "serving:read",
                    "serving:write",
                }
            ),
        )


def build_verifier(settings: Settings) -> TokenVerifier:
    if not settings.auth_enabled:
        return AllowAllTokenVerifier()
    if settings.jwt_jwks_url:
        return JwksTokenVerifier(
            settings.jwt_jwks_url,
            settings.jwt_algorithm,
            settings.jwt_issuer,
            settings.jwt_audience,
        )
    return HS256TokenVerifier(settings.jwt_secret, settings.jwt_issuer, settings.jwt_audience)
