# Architecture

## Layering and dependency rules

The codebase enforces Clean Architecture. Dependencies point inward only.

- `domain` depends on nothing outside itself.
- `application` depends on `domain` (including its ports), never on `infrastructure`
  or `presentation`.
- `infrastructure` implements the ports declared in `domain` and `application`.
- `presentation` depends on `application` and, at the composition root only, wires
  `infrastructure` implementations into the ports.

The composition root is `presentation/api/app.py`. It is the single place where
concrete adapters (SQLAlchemy unit of work, Redis cache, JWT verifier) are constructed
and attached to application state. Request handlers receive collaborators through
dependency injection and never import concrete infrastructure.

## Folder map

```
src/cascade/
  domain/
    common/          Entity, AggregateRoot, DomainEvent, base errors
    pipelines/       Pipeline aggregate, value objects, events, repository port
  application/
    common/          UnitOfWork port, Page, application errors
    pipelines/       commands, queries, DTOs, PipelineApplicationService
  infrastructure/
    config.py        pydantic-settings configuration (12-factor)
    logging.py       structlog wiring
    telemetry.py     OpenTelemetry tracing
    metrics.py       Prometheus registry and metrics
    database/        engine, ORM models, mappers, SQLAlchemy unit of work
    repositories/    SQLAlchemy repository implementations
    cache/           cache port and Redis implementation
    security/        JWT verification and Principal
  presentation/api/
    app.py           application factory and composition root
    dependencies.py  DI providers
    security.py      auth dependency and RBAC scope guard
    errors.py        RFC 7807 exception handlers
    middleware/      correlation id, access log and metrics, rate limiting
    schemas/         pydantic request and response models
    routers/         health and pipeline endpoints
```

## The Pipeline aggregate

`Pipeline` is the consistency boundary. It owns its state machine:

```
draft ---activate--> active ---pause--> paused
  |                     |                  |
  |                     `----activate------'
  |                     |
  `------archive--------+------archive-----> archived (terminal)
```

Invalid transitions raise `InvalidStateTransition`. Every successful transition records
a `PipelineStatusChanged` domain event; registration records `PipelineRegistered`.
Events are pulled and logged by the application service after commit. A durable outbox
and event bus are introduced in Phase 2.

## Cross-cutting concerns

- Correlation id: generated or propagated per request, bound to the log context, and
  echoed in the `X-Correlation-ID` response header.
- Errors: every failure maps to an RFC 7807 problem document with the correlation id.
- Idempotency: `POST /api/v1/pipelines` stores the response under a namespaced
  `Idempotency-Key` so retries replay the original result.
- Rate limiting: a Redis token bucket keyed by client identity, with `Retry-After` on
  rejection.
- Concurrency: aggregates carry a version; updates use an optimistic version check and
  raise `ConcurrencyError` on conflict.

## Observability

- Logs: structured JSON via structlog, correlation id merged from context.
- Metrics: `http_requests_total` and `http_request_duration_seconds` on `/metrics`.
- Traces: OpenTelemetry spans exported over OTLP/HTTP when `CASCADE_OTEL_ENABLED=true`,
  with FastAPI and SQLAlchemy auto-instrumentation.
- Probes: `/livez` for liveness and `/readyz` for readiness (checks database and Redis).
