# Lakehouse, transformations, and data quality

The lakehouse context is where the control plane manages the medallion tables that make up
the analytical layer: bronze holds raw landed data, silver holds cleaned and conformed
data, and gold holds curated, business-facing data. Cascade does not run the SQL itself.
dbt builds the tables and Airflow decides when, so what the control plane owns is the
governed definition of each dataset, its lineage, its schedule, and the quality rules that
decide whether a materialization is trustworthy. Two rules are enforced here rather than
left to convention: medallion layering and the data-quality gate.

## The Dataset aggregate

`Dataset` is the consistency boundary. It holds a dotted table name (for example
`silver.orders_enriched`), a medallion layer, a dbt transformation, upstream dataset
dependencies, an Airflow schedule, a set of quality checks, an optional governing contract,
and the results of the last run. A dataset always starts in the `registered` state; nothing
is built until it is materialized.

The lifecycle is an explicit state machine, and illegal moves raise
`InvalidDatasetTransition` in the domain.

```
registered    -> materializing, deprecated
materializing -> materialized, failed, deprecated
materialized  -> materializing, stale, deprecated
stale         -> materializing, deprecated
failed        -> materializing, deprecated
deprecated    -> (terminal)
```

## The medallion invariant

Data in a lakehouse should flow one way: bronze to silver to gold. The aggregate enforces
this at registration by rejecting any dependency on a higher layer. A silver dataset may
depend on bronze or silver, a gold dataset on any lower layer, but a silver dataset may not
depend on a gold one, and a bronze dataset may not depend on silver or gold. Self
dependencies and duplicate dependencies are rejected too. Because the rule needs each
upstream's layer, the application service resolves every upstream id to the real dataset
first (which also verifies it exists), then hands typed references to the aggregate, which
makes the decision.

## The data-quality gate

Quality checks are declared per dataset: not-null and unique on a column, accepted values,
a minimum row count, or a freshness bound. When a materialization completes, the
transformation runtime returns an outcome for each check, and the aggregate evaluates them
in one place: if any check fails, the dataset moves to `failed` with quality status
`failed` rather than to `materialized`. This means a run that produced rows but violated a
contract of quality is treated as a failure, which is the behaviour a downstream consumer
wants. A runtime error (dbt itself failing) also lands the dataset in `failed`, with the
reason recorded.

## Lineage and staleness

Dependencies form a DAG, and the control plane keeps it coherent. After a dataset
rematerializes successfully, the service finds the datasets that depend on it and marks any
that were `materialized` as `stale`, because their inputs just changed. Staleness is a
signal, not a cascade: a stale dataset is simply flagged for a rebuild on its next
scheduled or manual run. Lineage is queryable directly: the lineage endpoint returns a
dataset's declared upstreams and, by a reverse lookup, its downstream dependents.

## The runtime ports

Two external systems sit behind ports.

- `TransformationRuntime` (dbt) has a `run` method returning a run reference, a row count,
  and per-check quality outcomes. `InMemoryTransformationRuntime` is the default and needs
  no engine; `DbtCloudTransformationRuntime` triggers a dbt Cloud job run over HTTP.
  `build_dbt_run_config` translates a dataset into a dbt selector plus a test plan derived
  from the quality checks.
- `Orchestrator` (Airflow) manages schedules (`upsert_schedule`, `pause`), triggers runs,
  and reports status. `InMemoryOrchestrator` is the default; `AirflowOrchestrator` maps a
  schedule to a DAG and its paused flag over the Airflow REST API.

The adapters are chosen by configuration: set the dbt Cloud settings or the Airflow
settings to use the real systems, leave them unset to stay in memory.

## Cross-context integrity

A dataset may reference a data contract for the schema it produces. When it does, the
application service checks the contract exists, and the database enforces it with a nullable
foreign key from `datasets.contract_id` to `data_contracts.id` (on delete set null).

## Endpoints

| Method | Path                                     | Scope             |
| ------ | ---------------------------------------- | ----------------- |
| POST   | `/api/v1/datasets`                       | `lakehouse:write` |
| GET    | `/api/v1/datasets`                       | `lakehouse:read`  |
| GET    | `/api/v1/datasets/{id}`                  | `lakehouse:read`  |
| GET    | `/api/v1/datasets/{id}/lineage`          | `lakehouse:read`  |
| POST   | `/api/v1/datasets/{id}/materialize`      | `lakehouse:write` |
| PUT    | `/api/v1/datasets/{id}/schedule`         | `lakehouse:write` |
| POST   | `/api/v1/datasets/{id}/deprecate`        | `lakehouse:write` |

Registration is idempotent via the `Idempotency-Key` header. List supports filtering by
`layer`, `status`, `quality_status`, and `contract_id`, with the usual pagination and sort.
