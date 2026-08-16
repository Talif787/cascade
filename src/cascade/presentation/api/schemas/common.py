from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ProblemDetails(BaseModel):
    """RFC 7807 problem response."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    correlation_id: str | None = None


class PageMeta(BaseModel):
    page: int
    size: int
    total: int
    pages: int


class PaginatedResponse(BaseModel, Generic[T]):  # noqa: UP046 (pydantic generic model)
    items: list[T]
    meta: PageMeta


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    checks: dict[str, str] = Field(default_factory=dict)
