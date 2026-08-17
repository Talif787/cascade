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
    contracts/       DataContract aggregate, schema value objects, compatibility engine
    ingestion/       IngestionSource aggregate, connector value objects, dead-letter policy
  application/
    common/          UnitOfWork port, Page, application errors
    pipelines/       commands, queries, DTOs, PipelineApplicationService
    contracts/       commands, queries, DTOs, SchemaRegistry port, service
    ingestion/       commands, queries, DTOs, ConnectorRuntime port, service
  infrastructure/
    config.py        pydantic-settings configuration (12-factor)
    logging.py       structlog wiring
    telemetry.py     OpenTelemetry tracing
    metrics.py       Prometheus registry and metrics
    database/        engine, ORM models, mappers, SQLAlchemy unit of work
    repositories/    SQLAlchemy repository implementations
    registry/        schema serialization and in-memory / Confluent adapters
    connect/         connector runtime: in-memory and Kafka Connect adapters
    cache/           cache port and Redis implementation
    security/        JWT verification and Principal
  sdk/               standalone producer client and record validator (httpx + stdlib only)
  presentation/api/
    app.py           application factory and composition root
    dependencies.py  DI providers
    security.py      auth dependency and RBAC scope guard
    errors.py        RFC 7807 exception handlers
    middleware/      correlation id, access log and metrics, rate limiting
    schemas/         pydantic request and response models
    routers/         health, pipeline, and contract endpoints
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
and event bus arrive in a later phase.

## The DataContract aggregate

`DataContract` governs the schema of a dataset. It owns an ordered list of `SchemaVersion`
entities and enforces a single invariant on every publish: the candidate schema must be
compatible with the latest published version under the contract's compatibility mode. That
rule lives in `domain/contracts/compatibility.py` as a pure function over two schema
definitions, so it is deterministic and unit-testable without any infrastructure.

Compatibility is expressed as a reader schema reading data written with a writer schema.
Backward compatibility checks that the new schema (reader) can read old data (writer);
forward flips the roles; full requires both. The direction is the subtle part: getting
reader and writer the wrong way round silently swaps backward and forward, so the two
directions are covered explicitly by the unit tests.

Publishing a version is orchestrated by the application service, not the domain: the
aggregate validates and appends the version, then the service registers the schema through
the `SchemaRegistry` port and stores the returned id on the version. The port has an
in-memory adapter (the default, so nothing external is required) and a Confluent-compatible
HTTP adapter selected when `CASCADE_SCHEMA_REGISTRY_URL` is set. See
`docs/data-contracts.md` for the full compatibility matrix and endpoint list.

## The IngestionSource aggregate

`IngestionSource` governs a managed connection to an external system. It owns a lifecycle
state machine (registered, provisioning, running, paused, failed, decommissioned) and a
dead-letter policy, and it references the data contract that governs its records plus an
optional pipeline it feeds. Illegal lifecycle moves raise `InvalidSourceTransition` in the
domain, and a dead-letter breach that trips the policy tolerance records an event and, for a
halt policy, drives the source to failed. All of that is pure and unit-testable.

The external connector system is abstracted behind the `ConnectorRuntime` port, following
the same pattern as the schema registry: an in-memory adapter is the default so the stack
and tests need no Kafka, and a `KafkaConnectRuntime` adapter drives the Kafka Connect REST
API (including Debezium connector classes) when `CASCADE_KAFKA_CONNECT_URL` is set.
Provisioning is a two-step orchestration in the application service so that stored state
always follows what the runtime actually did. Cross-context references are enforced both at
registration and with database foreign keys. The producer SDK under `sdk/` is intentionally
kept free of any server dependency so a data-plane producer can vendor it. See
`docs/ingestion.md` for the state machine, dead-letter semantics, and endpoint list.

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
