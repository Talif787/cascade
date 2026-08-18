from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class TranslationError(RuntimeError):
    """Raised when the translator cannot produce a structured query."""


@dataclass(frozen=True, slots=True)
class TranslationColumn:
    name: str
    role: str
    type: str


@dataclass(frozen=True, slots=True)
class TranslationSchema:
    view_name: str
    columns: tuple[TranslationColumn, ...]


@dataclass(frozen=True, slots=True)
class TranslatedMeasureSpec:
    column: str
    aggregation: str


@dataclass(frozen=True, slots=True)
class TranslatedFilterSpec:
    column: str
    op: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TranslationResult:
    dimensions: tuple[str, ...] = field(default_factory=tuple)
    measures: tuple[TranslatedMeasureSpec, ...] = field(default_factory=tuple)
    filters: tuple[TranslatedFilterSpec, ...] = field(default_factory=tuple)
    limit: int = 100
    notes: str = ""


class Nl2SqlTranslator(ABC):
    """Port that turns a natural-language question into a structured query.

    The translator only proposes columns, aggregations, and filters; the
    application layer validates the proposal against the serving view's declared
    schema before anything runs, so a hallucinated column cannot reach the data.
    """

    @abstractmethod
    async def translate(self, question: str, schema: TranslationSchema) -> TranslationResult: ...
