# Local development

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- `make`

## Setup

```bash
cp .env.example .env
make install          # editable install with dev extras
```

## Running against the Compose stack

```bash
make up               # postgres, redis, jaeger, prometheus, api
```

- API and docs: http://localhost:8000/docs
- Jaeger UI: http://localhost:16686
- Prometheus: http://localhost:9090

Tear down with `make down` (this also removes volumes).

## Running the API on the host

Start only the backing services, then run the app directly:

```bash
docker compose up -d postgres redis
make migrate
make seed
make run
```

## Everyday commands

```bash
make fmt          # format and auto-fix
make lint         # ruff
make typecheck    # mypy
make test         # unit and API tests (no external services)
make cov          # tests with coverage
make test-integration  # repository tests against a throwaway Postgres
```

## Creating a new migration

After changing ORM models:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Review the generated migration before committing. Autogenerate is a starting point,
not a substitute for reading the diff.

## Authentication in development

The Compose stack sets `CASCADE_AUTH_ENABLED=false`. When you enable auth, mint an
HS256 token whose `scope` claim contains `pipelines:read pipelines:write` and send it as
`Authorization: Bearer <token>`.
