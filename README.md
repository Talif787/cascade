# Cascade Control Plane

The Cascade control plane is the governance and metadata service for the Cascade
real-time streaming data platform. It registers and governs data pipelines, and in
later phases it will manage data contracts, provision connectors, orchestrate stream
processing jobs, and serve platform metadata. The compute-heavy data plane (Kafka,
Debezium, Flink, Iceberg) scales horizontally on its own and is layered in over the
phases described below.

This repository currently contains Phases 1 and 2: the control-plane foundation with a
complete vertical slice for the Pipeline aggregate, plus the Data Contracts bounded
context with a schema compatibility engine and pluggable schema registry.

## Why a modular monolith

A streaming platform has two very different halves. The data plane is already
distributed and elastic. The control plane is a cohesive, transactional, low-QPS
system. Splitting the control plane into microservices this early would introduce
distributed transactions and operational overhead with no scaling benefit. The
control plane is therefore a modular monolith: one deployable, with strict internal
module boundaries so any bounded context (pipelines, contracts, connectors) can be
extracted into its own service later without a rewrite.

## Technology choices

- Python 3.12 and FastAPI: async, first-class OpenAPI generation, and a natural home
  next to the Python data tooling introduced in later phases. The JVM is reserved for
  Flink and Spark jobs where it belongs.
- PostgreSQL: strong consistency and transactions for control-plane metadata, with
  JSONB for flexible connector configuration.
- Redis: caching, durable idempotency keys, and distributed token-bucket rate limiting.
- SQLAlchemy 2.0 (async) and Alembic: typed data mapping and versioned migrations.
- structlog, OpenTelemetry, and Prometheus: structured logs, distributed traces, and
  metrics.
- JWT and OIDC: bearer authentication against an external identity provider in
  production (for example Keycloak), with HS256 for local development.
- REST over GraphQL: control-plane operations are resource and lifecycle oriented and
  benefit from HTTP caching and idempotency semantics. GraphQL is deferred to the
  analytics serving layer where flexible querying matters.
- GitHub Actions: the repository targets GitHub, so a single provider keeps CI, code,
  and releases together.

## Architecture

The service follows Clean Architecture with strict dependency inversion:

```
presentation  ->  application  ->  domain
        \\             |              ^
         \\            v              |
          `------> infrastructure ----'  (implements domain and application ports)
```

- `domain`: aggregates, value objects, invariants, domain events, and repository
  ports. Pure Python with no framework dependencies.
- `application`: use cases expressed as commands and queries, orchestrating the domain
  through a unit of work and returning DTOs. Translates domain errors into application
  errors.
- `infrastructure`: configuration, logging, telemetry, metrics, the SQLAlchemy
  persistence adapters, the Redis cache, and the JWT verifier.
- `presentation`: the FastAPI application, dependency injection, middleware, RFC 7807
  error handling, request and response schemas, RBAC, and health probes.

Everything is wired at a single composition root
(`presentation/api/app.py` and `dependencies.py`). Because the application depends only
on ports, the API test suite swaps in in-memory adapters through those same ports and
runs with no external services.

See `docs/architecture.md` for the folder map and dependency rules in detail.

## Quick start

Requirements: Docker and Docker Compose.

```bash
cp .env.example .env
make up          # starts postgres, redis, jaeger, prometheus, and the API
```

The API applies migrations on start and listens on http://localhost:8000.
Interactive docs: http://localhost:8000/docs. In the Compose stack authentication is
disabled for convenience (`CASCADE_AUTH_ENABLED=false`).

Local (without containers for the app):

```bash
make install
make migrate
make seed
make run
```

## Example requests

```bash
# Register a pipeline (auth disabled locally)
curl -X POST http://localhost:8000/api/v1/pipelines \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-1" \
  -d '{
        "name": "orders-cdc-to-lake",
        "source": {"type": "postgres_cdc", "resource": "public.orders"},
        "sink": {"type": "iceberg", "resource": "bronze.orders"}
      }'

# List with pagination and filtering
curl "http://localhost:8000/api/v1/pipelines?page=1&size=20&status=draft"
```

## API surface

| Method | Path                                              | Scope             |
| ------ | ------------------------------------------------- | ----------------- |
| POST   | `/api/v1/pipelines`                               | `pipelines:write` |
| GET    | `/api/v1/pipelines`                               | `pipelines:read`  |
| GET    | `/api/v1/pipelines/{id}`                          | `pipelines:read`  |
| POST   | `/api/v1/pipelines/{id}/activate`                 | `pipelines:write` |
| POST   | `/api/v1/pipelines/{id}/pause`                    | `pipelines:write` |
| POST   | `/api/v1/pipelines/{id}/archive`                  | `pipelines:write` |
| POST   | `/api/v1/contracts`                               | `contracts:write` |
| GET    | `/api/v1/contracts`                               | `contracts:read`  |
| GET    | `/api/v1/contracts/{id}`                          | `contracts:read`  |
| GET    | `/api/v1/contracts/{id}/versions/{version}`       | `contracts:read`  |
| POST   | `/api/v1/contracts/{id}/versions`                 | `contracts:write` |
| POST   | `/api/v1/contracts/{id}/compatibility`            | `contracts:read`  |
| PUT    | `/api/v1/contracts/{id}/compatibility-mode`       | `contracts:write` |
| POST   | `/api/v1/contracts/{id}/versions/{version}/deprecate` | `contracts:write` |
| POST   | `/api/v1/contracts/{id}/deprecate`                | `contracts:write` |
| GET    | `/livez`, `/readyz`, `/metrics`                   | none              |

The OpenAPI 3.1 document is served at `/openapi.json`. Errors follow RFC 7807
(`application/problem+json`) and carry the correlation id. Registration is idempotent
via the `Idempotency-Key` header. A rejected schema publish returns 409 with the
`compatibility_mode` and the list of `violations`.

## Testing

```bash
make test              # unit + API, no external services required
make cov               # with coverage
make test-integration  # repository tests against a throwaway Postgres (needs Docker)
```

## Deployment (Phase 1 scope)

The service ships as a single container image built from the multi-stage `Dockerfile`
(non-root user, healthcheck on `/livez`). Migrations run as a pre-start step
(`alembic upgrade head`). Full Kubernetes manifests, Helm charts, and Terraform arrive
in Phase 9.

## Roadmap

1. Control-plane foundation and Pipeline slice (done).
2. Data Contracts and Schema Registry integration (done).
3. Ingestion data plane: Debezium, Kafka Connect, producer SDK, dead-letter queues.
4. Stream processing: Flink jobs with exactly-once Iceberg sinks.
5. Lakehouse and transformations: Iceberg medallion tables, dbt, Airflow, data quality.
6. Serving: ClickHouse OLAP, query API, live updates.
7. Observability and governance: lineage, freshness SLAs, cost dashboards.
8. AI-native layer: NL2SQL copilot and a governed data MCP server.
9. Platform hardening: Kubernetes, Helm, Terraform, GitOps, supply-chain security.

## Documentation

- `docs/architecture.md`
- `docs/data-contracts.md`
- `docs/configuration.md`
- `docs/local-development.md`
- `docs/runbook.md`
