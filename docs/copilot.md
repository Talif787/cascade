# Copilot: natural language to a governed query

The copilot lets someone ask a question in plain language and get an answer from a serving
view, without writing SQL and without the risk that a language model invents a column or a
join. The design principle is simple: the model proposes, the domain disposes. A translator
suggests a structured query using only the columns the view declares, and the serving view
validates that suggestion with the same rules that guard the serving API before anything
runs.

## The flow

1. A question arrives naming a target serving view (by id or name).
2. The service builds a schema descriptor from the view's declared columns (name, role, type)
   and hands it, with the question, to the `Nl2SqlTranslator` port.
3. The translator returns a structured proposal: dimensions, measures with aggregations,
   filters, and a limit. It only ever names columns; it cannot emit raw SQL.
4. The service turns the proposal into a serving query request and calls the view's
   `plan_query`. This is the governance gate: an unknown column, a measure used as a
   dimension, or a query against a view that is not ready is rejected here, by the same domain
   code the serving API uses.
5. If validation passes and execution was requested, the validated plan runs through the
   ClickHouse runtime and the rows come back. If not, the query is recorded as translated but
   not executed.
6. Every ask is persisted as a `CopilotQuery` audit record regardless of outcome.

## The aggregate

`CopilotQuery` records the question, the target view, the translated query, the outcome, and
a row count or rejection reason. Its lifecycle is a small state machine: asked, then either
translated or rejected; a translated query is then either executed or failed. The states are
terminal where they should be, so the audit trail cannot be rewritten. This record is what
makes the copilot governable after the fact: every question, what it was translated to, and
whether it ran is queryable.

## The translator port

`Nl2SqlTranslator` has two adapters. The rule-based translator is the default and needs no
external service: it matches aggregation keywords (total, average, count, and so on), detects
group-by dimensions from phrases like "by region", picks up simple equality filters, honors a
"top N" limit, and falls back to a dimension preview for browse-style questions. It is
deterministic, which makes the whole copilot path testable without a network call. The LLM
adapter sends the schema and question to an OpenAI-compatible endpoint and parses a strict
JSON proposal. Both produce the same proposal shape, and both are subject to the same
validation, so switching between them changes translation quality, not the safety guarantees.

The adapter is chosen by configuration: set `CASCADE_COPILOT_API_URL` and
`CASCADE_COPILOT_API_KEY` to use the LLM, leave them unset to use the rule-based translator.

## Why validation lives in the serving view

The copilot deliberately does not re-implement query checking. It reuses the serving view's
`plan_query`, so the guarantees are identical to the serving API: only declared columns,
correct roles, and a queryable view. A model that hallucinates a column name cannot reach the
data, because the proposal is rejected before compilation. The copilot adds translation and
an audit trail on top of the serving guardrails; it does not weaken them.

## Endpoints

| Method | Path                              | Scope           |
| ------ | --------------------------------- | --------------- |
| POST   | `/api/v1/copilot/ask`             | `copilot:write` |
| GET    | `/api/v1/copilot/queries`         | `copilot:read`  |
| GET    | `/api/v1/copilot/queries/{id}`    | `copilot:read`  |

The ask body takes a question, a target view (`view_id` or `view_name`), and an optional
`execute` flag; setting it false returns the translation without running it, which is useful
for previewing what a question would do. List supports filtering by status and view.
