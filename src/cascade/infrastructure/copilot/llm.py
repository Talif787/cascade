from __future__ import annotations

import json
from typing import Any

import httpx

from cascade.application.copilot.translator import (
    Nl2SqlTranslator,
    TranslatedFilterSpec,
    TranslatedMeasureSpec,
    TranslationError,
    TranslationResult,
    TranslationSchema,
)

_SYSTEM_PROMPT = (
    "You translate a natural-language analytics question into a strict JSON object. "
    "You may only reference the columns provided. Respond with JSON of the shape "
    '{"dimensions": [str], "measures": [{"column": str, "aggregation": str}], '
    '"filters": [{"column": str, "op": str, "values": [str]}], "limit": int}. '
    "Aggregation is one of sum, avg, min, max, count. Operator is one of eq, neq, "
    "gt, gte, lt, lte, in. Do not include any prose outside the JSON object."
)


class LlmTranslator(Nl2SqlTranslator):
    """Adapter that asks an LLM to propose a structured query.

    The model only ever proposes columns; the application layer validates the
    proposal against the serving view schema before running it, so a wrong or
    invented column is rejected rather than executed.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    async def translate(self, question: str, schema: TranslationSchema) -> TranslationResult:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(question, schema)},
            ],
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise TranslationError(f"llm request failed: {exc}") from exc
        if response.status_code >= 400:
            raise TranslationError(f"llm returned {response.status_code}: {response.text}")
        body: dict[str, Any] = response.json()
        return _parse_completion(body)


def _user_prompt(question: str, schema: TranslationSchema) -> str:
    columns = "\n".join(f"- {c.name} (role={c.role}, type={c.type})" for c in schema.columns)
    return (
        f"View: {schema.view_name}\nColumns:\n{columns}\n\nQuestion: {question}\n"
        "Return only the JSON object."
    )


def _parse_completion(body: dict[str, Any]) -> TranslationResult:
    try:
        choices = body["choices"]
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TranslationError("llm response was not in the expected shape") from exc
    return _parse_result(content)


def _parse_result(content: str) -> TranslationResult:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TranslationError("llm did not return valid JSON") from exc
    if not isinstance(data, dict):
        raise TranslationError("llm JSON was not an object")

    dimensions = tuple(str(d) for d in data.get("dimensions", []))
    measures = tuple(
        TranslatedMeasureSpec(column=str(m["column"]), aggregation=str(m["aggregation"]))
        for m in data.get("measures", [])
        if isinstance(m, dict) and "column" in m and "aggregation" in m
    )
    filters = tuple(
        TranslatedFilterSpec(
            column=str(f["column"]),
            op=str(f["op"]),
            values=tuple(str(v) for v in f.get("values", [])),
        )
        for f in data.get("filters", [])
        if isinstance(f, dict) and "column" in f and "op" in f
    )
    limit = int(data.get("limit", 100)) if str(data.get("limit", "")).isdigit() else 100
    return TranslationResult(
        dimensions=dimensions,
        measures=measures,
        filters=filters,
        limit=limit,
        notes="translated by llm",
    )
