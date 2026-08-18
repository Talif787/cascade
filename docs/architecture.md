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
    processing/      StreamJob aggregate, checkpoint config, source/sink value objects
    lakehouse/       Dataset aggregate, medallion layers, transformation, schedule, quality
    serving/         ServingView aggregate, ClickHouse engine, exposed columns, query plan
    governance/      ServiceLevelObjective and CostEntry aggregates, asset refs, compliance
  application/
    common/          UnitOfWork port, Page, application errors
    pipelines/       commands, queries, DTOs, PipelineApplicationService
    contracts/       commands, queries, DTOs, SchemaRegistry port, service
    ingestion/       commands, queries, DTOs, ConnectorRuntime port, service
    processing/      commands, queries, DTOs, FlinkRuntime port, service
    lakehouse/       commands, queries, DTOs, TransformationRuntime + Orchestrator ports, service
    serving/         commands, queries, DTOs, ClickHouseRuntime port, service
    governance/      commands, queries, DTOs, CostSource port, lineage read model, service
  infrastructure/
    config.py        pydantic-settings configuration (12-factor)
    logging.py       structlog wiring
    telemetry.py     OpenTelemetry tracing
    metrics.py       Prometheus registry and metrics
    database/        engine, ORM models, mappers, SQLAlchemy unit of work
    repositories/    SQLAlchemy repository implementations
    registry/        schema serialization and in-memory / Confluent adapters
    connect/         connector runtime: in-memory and Kafka Connect adapters
    flink/           Flink runtime: in-memory and Flink REST adapters, job config builder
    transform/       transformation runtime: in-memory and dbt Cloud adapters, dbt run builder
    orchestrate/     orchestrator: in-memory and Airflow REST adapters
    clickhouse/      ClickHouse runtime: in-memory (executes queries) and HTTP adapters, SQL builder
    cost/            cost source: in-memory (synthetic) and HTTP billing adapters
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

## The StreamJob aggregate

`StreamJob` governs a Flink stream-processing job. It owns a lifecycle state machine
(defined, submitted, running, restarting, suspended, failed, completed, cancelled), a
checkpoint configuration, a restart strategy, a source, and a sink, and it optionally
references the data contract for the schema it processes. The defining invariant, enforced
in the domain at `define()` and re-checked whenever the checkpoint config changes, is that
a sink which needs exactly-once (Iceberg) requires the exactly-once delivery guarantee with
checkpointing enabled, because Flink commits Iceberg writes in step with its checkpoints.
Pairing an Iceberg sink with at-least-once is rejected as invalid input.

The Flink cluster is abstracted behind the `FlinkRuntime` port, following the same pattern
as the schema registry and connector runtime: an in-memory adapter is the default so the
stack and tests need no Flink, and a `FlinkRestRuntime` adapter drives the Flink REST API
when `CASCADE_FLINK_REST_URL` is set. Suspend maps to a stop-with-savepoint, and the
returned savepoint path is stored so resume can restart the job from exactly that state,
which is how exactly-once survives an operator-driven restart. Submission is a two-step
orchestration so stored state follows what the cluster actually did. See
`docs/processing.md` for the state machine, exactly-once rules, and endpoint list.

## The Dataset aggregate

`Dataset` governs a medallion Iceberg table. It owns a materialization lifecycle
(registered, materializing, materialized, stale, failed, deprecated), a dbt transformation,
an Airflow schedule, a set of data-quality checks, and its upstream dataset dependencies.
The defining invariant, enforced in the domain at registration, is the medallion rule: a
dataset may depend only on datasets in the same or a lower layer (bronze, then silver, then
gold), never a higher one, and never on itself. Data quality is wired into the lifecycle:
when a materialization completes, the quality outcomes are evaluated, and any failure moves
the dataset to failed rather than materialized.

Two external systems sit behind ports, following the established pattern. The
`TransformationRuntime` (dbt) materializes a dataset and returns a row count plus quality
outcomes; it has an in-memory default and a dbt Cloud adapter. The `Orchestrator` (Airflow)
manages schedules and triggers runs; it has an in-memory default and an Airflow REST
adapter. The application service also keeps lineage coherent: after a successful
rematerialization it marks lineage-downstream datasets stale, and it exposes upstream and
downstream lineage through a dedicated query. See `docs/lakehouse.md` for the medallion
rules, quality semantics, and endpoint list.

## The ServingView aggregate

`ServingView` governs a ClickHouse-backed table that serves curated data to the analytics
frontend. It references a source dataset from the lakehouse, and it owns a ClickHouse
engine, an exposed set of columns (each tagged as a dimension, measure, or time column), an
order-by key, a refresh mode, and a sync lifecycle (registered, syncing, ready, stale,
failed, retired). One invariant lives in the domain: the aggregating engines
(SummingMergeTree, AggregatingMergeTree) require at least one measure column, since they
exist to roll measures up.

The distinctive capability is a constrained analytics query. Rather than accepting raw SQL,
the aggregate validates a structured request (dimensions, measures with aggregations,
filters) against its declared columns and roles: a measure cannot be selected as a
dimension, an unknown column is rejected, and a view can only be queried once it is ready or
stale. The validated plan is compiled to a neutral query and handed to the `ClickHouseRuntime`
port. The in-memory adapter executes that query in process (filter, group-by, aggregate)
over synthetic rows, so the whole query path is exercised by tests without a cluster; the
HTTP adapter turns the plan into ClickHouse SQL. Staleness against the source is explicit:
`reconcile` compares the source dataset's last materialization with the view's last sync and
marks the view stale when the source is newer. A catalog query lists the ready views and
their columns, which is what the frontend reads to discover what it can query. See
`docs/serving.md` for the engine rules, the query model, and the endpoint list.

## The governance layer

The governance context layers observability over the assets the other contexts produce. It
holds two aggregates and one read model. The `ServiceLevelObjective` aggregate binds a
freshness target to a refreshable asset (a dataset or serving view, enforced as a domain
invariant) and evaluates compliance against the asset's last refresh: meeting, at risk (past
eighty percent of the target), or breached, incrementing a breach count only on a fresh
breach. Evaluation is a domain method fed the asset's last refresh time, which the service
reads from the dataset's last materialization or the serving view's last sync. The
`CostEntry` aggregate is an immutable record of cost attributed to an asset and category over
a period; entries are recorded directly or imported through the `CostSource` port (in-memory
synthetic by default, an HTTP billing adapter when configured), and the repository rolls them
up by category and by asset into a cost report through SQL aggregation. Lineage is a read
model with no table of its own: it walks the dataset upstream references, dataset dependents,
and serving-view sources already present in the other contexts to assemble a node and edge
graph rooted at any asset.

Cross-context references here are polymorphic `(kind, id)` pairs rather than foreign keys,
since a governed asset can live in any of several tables. The service validates that a
referenced asset exists by dispatching to the right repository for its kind, so integrity is
enforced in the application layer rather than the schema. See `docs/governance.md` for the
compliance model, the cost flow, and the endpoint list.

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
