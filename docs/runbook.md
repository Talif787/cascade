# Operational runbook

## Health and readiness

- `GET /livez` returns 200 while the process is running. Use it for liveness probes.
- `GET /readyz` returns 200 only when Postgres and Redis are reachable, otherwise 503
  with a per-dependency breakdown. Use it for readiness probes and to gate traffic.
- `GET /metrics` exposes Prometheus metrics.

## Golden signals

- Request rate and errors: `http_requests_total` by `status`.
- Latency: `http_request_duration_seconds` histogram (watch p95 and p99).
- Saturation: database pool usage and Redis latency.

Every log line and error response carries a `correlation_id`. Start any investigation
by filtering logs on the correlation id from the affected response.

## Common situations

### Readiness is failing (503 on /readyz)

1. Check which dependency is `unavailable` in the `/readyz` body.
2. Database: confirm `CASCADE_DATABASE_URL`, network reachability, and that migrations
   have been applied (`alembic upgrade head`).
3. Redis: confirm `CASCADE_REDIS_URL` and that Redis is accepting connections.

### 401 Unauthorized

- A valid bearer token is required when `CASCADE_AUTH_ENABLED=true`. Verify the token
  signature, `iss`, `aud`, and expiry, and that JWKS configuration matches the issuer.

### 403 Forbidden

- The token is valid but lacks a required scope. Pipeline writes need
  `pipelines:write`; reads need `pipelines:read`.

### 409 Conflict

- Either a duplicate pipeline name, an invalid state transition (for example pausing a
  draft pipeline), or an optimistic-concurrency conflict. The problem `detail` field
  distinguishes them.

### 429 Too Many Requests

- The client exceeded its token bucket. Honor the `Retry-After` header. Adjust
  `CASCADE_RATE_LIMIT_PER_MINUTE` and `CASCADE_RATE_LIMIT_BURST` if limits are wrong.

## Migrations and rollback

- Apply: `alembic upgrade head`.
- Roll back one revision: `alembic downgrade -1`.
- Migrations run as a pre-start step. If a deploy fails during migration, the previous
  image remains healthy; fix forward with a new migration where possible rather than
  downgrading a live database.

## Deploy and rollback (Phase 1 scope)

- The service is a stateless container. Roll back by redeploying the previous image
  tag. Because schema changes are gated by migrations, keep migrations backward
  compatible within a release window (expand, migrate, contract).
