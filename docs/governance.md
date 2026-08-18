# Governance: freshness SLOs, cost, and lineage

The governance context is cross-cutting. Where the earlier contexts each own a slice of the
platform, governance layers observability over all of them: it answers whether data is fresh
enough, what the platform costs, and how assets connect. It owns two aggregates and one read
model, and it references assets in the other contexts without coupling their schemas
together.

## Asset references

A governed concern points at an asset through an `AssetRef`, a `(kind, id)` pair where kind
is one of pipeline, ingestion source, stream job, dataset, or serving view. Because an asset
can live in any of several tables, references are not foreign keys. The application service
validates existence by dispatching to the right repository for the kind, so referential
integrity is enforced in the application layer. This keeps governance decoupled: it can
observe any asset without the other contexts depending on it.

## Freshness SLOs

`ServiceLevelObjective` binds a freshness target to a refreshable asset. Only datasets and
serving views are refreshable, and attaching a freshness SLO to any other kind is rejected in
the domain. The target is a maximum staleness in minutes; a warning threshold sits at eighty
percent of it.

Evaluation is a domain method that takes the asset's last refresh time and the current time
and returns a compliance state:

- meeting: staleness is within the warning threshold,
- at risk: staleness is past the warning threshold but within the target,
- breached: staleness is past the target, or the asset has never been refreshed.

The aggregate records each evaluation, and on a transition into breach (not on every
evaluation while breached) it increments a breach count and emits a breach event. The service
supplies the last refresh time by reading the dataset's last materialization or the serving
view's last sync, so governance reads freshness from the same timestamps the pipelines
maintain. SLOs have a lifecycle (active, suspended, retired); a suspended SLO is skipped by
evaluation, and evaluate-all walks every active SLO in one pass.

## Cost

`CostEntry` is an immutable record: an asset, a category (compute, storage, transfer), an
amount in cents, a period, and a source. Entries arrive two ways. They can be recorded
directly against an asset, or imported through the `CostSource` port, which abstracts a
billing export. The in-memory source returns synthetic observations for local development;
the HTTP adapter pulls from a billing endpoint. Import skips observations whose assets do not
exist, so a stale billing feed cannot create dangling cost records.

The cost report is a rollup. The repository aggregates entries with SQL `GROUP BY` into a
total, a breakdown by category, and a breakdown by asset, optionally bounded by a time
window. This is what a cost dashboard reads.

## Lineage

Lineage is a read model, not a stored graph. The other contexts already hold the edges: a
dataset lists its upstream datasets, and a serving view names its source dataset. The lineage
query walks those references from a root asset, collecting upstream datasets, downstream
dependents, and the serving views that read a dataset, and returns a node and edge graph.
Because it derives from live references, it never drifts from the actual topology, and it
needs no table or maintenance.

## Endpoints

| Method | Path                                          | Scope              |
| ------ | --------------------------------------------- | ------------------ |
| POST   | `/api/v1/governance/slos`                     | `governance:write` |
| GET    | `/api/v1/governance/slos`                     | `governance:read`  |
| POST   | `/api/v1/governance/slos/evaluate`            | `governance:write` |
| GET    | `/api/v1/governance/slos/{id}`                | `governance:read`  |
| POST   | `/api/v1/governance/slos/{id}/evaluate`       | `governance:write` |
| PUT    | `/api/v1/governance/slos/{id}/target`         | `governance:write` |
| POST   | `/api/v1/governance/slos/{id}/suspend`        | `governance:write` |
| POST   | `/api/v1/governance/slos/{id}/resume`         | `governance:write` |
| POST   | `/api/v1/governance/slos/{id}/retire`         | `governance:write` |
| POST   | `/api/v1/governance/costs`                    | `governance:write` |
| POST   | `/api/v1/governance/costs/import`             | `governance:write` |
| GET    | `/api/v1/governance/costs/report`             | `governance:read`  |
| GET    | `/api/v1/governance/lineage/{kind}/{id}`      | `governance:read`  |

The cost report accepts optional `window_start` and `window_end` ISO timestamps. The lineage
path takes an asset kind and id and returns the graph rooted there; an unknown root is a 404.
List supports filtering SLOs by asset kind, status, and compliance state.
