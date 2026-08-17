# Serving: ClickHouse views and the analytics query API

The serving context is the gate between the lakehouse and the analytics frontend. The
lakehouse produces curated gold tables, but those live in object storage and are not shaped
for interactive queries. The serving context manages ClickHouse-backed views that materialize
curated data into a fast columnar store and exposes a constrained query API the frontend can
call without writing SQL. What the control plane owns is the governed definition of each
served view, its sync lifecycle, and the rules that decide what can be queried and how.

## The ServingView aggregate

`ServingView` is the consistency boundary. It references a source dataset from the lakehouse,
and it holds a ClickHouse engine, an exposed schema (columns, each tagged dimension, measure,
or time, plus an order-by key and an optional partition key), a refresh mode, and the results
of the last sync. A view always starts in `registered`; nothing is queryable until it has
been synced.

The lifecycle is an explicit state machine, and illegal moves raise
`InvalidServingTransition` in the domain.

```
registered -> syncing, retired
syncing    -> ready, failed, retired
ready      -> syncing, stale, retired
stale      -> syncing, retired
failed     -> syncing, retired
retired    -> (terminal)
```

## The engine invariant

ClickHouse's aggregating engines (SummingMergeTree, AggregatingMergeTree) exist to roll up
measures along the order-by key. Declaring such an engine with no measure column is a
configuration mistake, so the aggregate rejects it at registration. The plain MergeTree and
ReplacingMergeTree engines have no such requirement.

## The constrained analytics query

This is the capability that gates the frontend. Rather than accepting raw SQL, a query is a
structured request: a set of dimensions to group by, a set of measures with aggregations
(sum, avg, min, max, count), and a set of filters. The aggregate validates the request
against its declared columns before anything runs: a dimension must be a declared
dimension or time column, a measure must be a declared measure, filter columns must exist,
and the view must be ready or stale. Only then is a query plan produced, its limit clamped to
a safe ceiling. This keeps the surface the frontend can reach small and safe, and it means a
malformed query is a 422 from the domain rather than a database error.

The validated plan is compiled to a neutral `CompiledQuery` and handed to the runtime. The
control plane never builds ClickHouse SQL in the application layer; that belongs to the
adapter.

## The ClickHouse runtime port

The cluster sits behind the `ClickHouseRuntime` port (create-or-replace, sync, drop, query).
Two adapters implement it:

- `InMemoryClickHouseRuntime` is the default. It stores tables in process, generates
  synthetic rows on sync, and actually executes the compiled query (filtering, grouping, and
  aggregating in Python). Because it runs the query for real, the entire query path is
  covered by tests with no ClickHouse cluster.
- `ClickHouseHttpRuntime` drives the ClickHouse HTTP interface. `build_create_table_sql`
  renders the DDL (engine, nullable types, partition and order keys), and `build_select_sql`
  renders the SELECT (grouped aggregations, escaped filter values, limit) from the compiled
  query.

The adapter is chosen by configuration: set `CASCADE_CLICKHOUSE_URL` to serve from a real
cluster, leave it unset to stay in memory.

## Staleness and the catalog

A serving view is a copy of curated data, so it can fall behind its source. Staleness is
explicit and reconcilable: `reconcile` loads the source dataset and, if its last
materialization is newer than the view's last sync, moves the view to `stale`. A stale view
is still queryable (the data is merely old); it signals that a resync is due. The catalog
query returns the ready views and their columns, which is what the frontend reads to discover
what it can query and how to shape a request.

## Cross-context integrity

A serving view must have a source dataset. The application service checks it exists at
registration, and the database enforces it with a foreign key from
`serving_views.source_dataset_id` to `datasets.id` with `ON DELETE RESTRICT`, so a dataset
that still backs a serving view cannot be deleted out from under it.

## Endpoints

| Method | Path                                      | Scope           |
| ------ | ----------------------------------------- | --------------- |
| POST   | `/api/v1/serving-views`                   | `serving:write` |
| GET    | `/api/v1/serving-views`                   | `serving:read`  |
| GET    | `/api/v1/serving-views/catalog`           | `serving:read`  |
| GET    | `/api/v1/serving-views/{id}`              | `serving:read`  |
| POST   | `/api/v1/serving-views/{id}/sync`         | `serving:write` |
| POST   | `/api/v1/serving-views/{id}/reconcile`    | `serving:write` |
| PUT    | `/api/v1/serving-views/{id}/schedule`     | `serving:write` |
| POST   | `/api/v1/serving-views/{id}/retire`       | `serving:write` |
| POST   | `/api/v1/serving-views/{id}/query`        | `serving:read`  |

Registration is idempotent via the `Idempotency-Key` header. The query endpoint is a POST
because it carries a request body, but it requires only the read scope since it reads data.
List supports filtering by `status`, `engine`, and `source_dataset_id`, with the usual
pagination and sort.
