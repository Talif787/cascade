from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from cascade.domain.copilot.errors import (
    InvalidCopilotQueryId,
    InvalidQuestion,
    InvalidTranslation,
)

_MAX_QUESTION_LEN = 2000


@dataclass(frozen=True, slots=True)
class CopilotQueryId:
    value: uuid.UUID

    @staticmethod
    def new() -> CopilotQueryId:
        return CopilotQueryId(uuid.uuid4())

    @staticmethod
    def from_string(raw: str) -> CopilotQueryId:
        try:
            return CopilotQueryId(uuid.UUID(raw))
        except (ValueError, AttributeError, TypeError) as exc:
            raise InvalidCopilotQueryId(str(raw)) from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Question:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise InvalidQuestion("must not be empty")
        if len(self.text) > _MAX_QUESTION_LEN:
            raise InvalidQuestion(f"must be at most {_MAX_QUESTION_LEN} characters")

    def __str__(self) -> str:
        return self.text


class CopilotStatus(StrEnum):
    ASKED = "asked"
    TRANSLATED = "translated"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TranslatedMeasure:
    column: str
    aggregation: str


@dataclass(frozen=True, slots=True)
class TranslatedFilter:
    column: str
    op: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TranslatedQuery:
    dimensions: tuple[str, ...] = field(default_factory=tuple)
    measures: tuple[TranslatedMeasure, ...] = field(default_factory=tuple)
    filters: tuple[TranslatedFilter, ...] = field(default_factory=tuple)
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.dimensions and not self.measures:
            raise InvalidTranslation(
                "a translated query must select at least one dimension or measure"
            )
        if self.limit < 1:
            raise InvalidTranslation("limit must be positive")
