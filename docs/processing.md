# Stream processing and exactly-once Iceberg sinks

The processing context is where the control plane manages the Flink jobs that transform
streams and land results in the lakehouse. As with connectors, the control plane does not
run the computation itself: a Flink cluster does. What the control plane owns is the
governed definition of each job, its lifecycle, and the checkpointing rules that make
its output correct. The headline rule of this phase lives here: an Iceberg sink is only
allowed with exactly-once delivery, and that is enforced in the domain rather than left to
operator discipline.

## The StreamJob aggregate

`StreamJob` is the consistency boundary. It holds a source, a sink, a delivery guarantee,
a checkpoint configuration, a restart strategy, a parallelism, an optional governing data
contract, a runtime reference (the Flink job id once submitted), and the location of the
last savepoint. A job always starts in the `defined` state; nothing runs until it is
explicitly submitted.

The lifecycle is an explicit state machine, and illegal moves raise `InvalidJobTransition`
inside the domain.

```
defined     -> submitted, cancelled
submitted   -> running, failed, cancelled
running     -> restarting, suspended, failed, completed, cancelled
restarting  -> running, failed, cancelled
suspended   -> running, cancelled
failed      -> restarting, cancelled
completed   -> (terminal)
cancelled   -> (terminal)
```

## The exactly-once invariant

Flink achieves exactly-once by checkpointing operator state and committing sink writes in
step with those checkpoints. The Iceberg sink relies on this two-phase commit, so an
Iceberg sink without exactly-once checkpointing would silently risk duplicates or partial
commits. The aggregate refuses to let that happen: at definition time, and again whenever
the checkpoint config is changed, it checks that a sink requiring exactly-once (Iceberg) is
paired with the exactly-once delivery guarantee, and that exactly-once implies checkpointing
is enabled. A violating definition is rejected as invalid input (422), not stored. Sinks
that do not need exactly-once (for example a Kafka topic) may run at-least-once.

## Savepoints, suspend, and resume

Suspend is a stop-with-savepoint: the control plane asks Flink to take a durable snapshot of
the job's state and stop, then stores the returned savepoint path on the aggregate. Resume
submits the job again from that exact path, so the job continues from where it left off with
no double-processing. A running job can also take an ad-hoc savepoint without stopping, which
records the path and leaves the job running. This is the mechanism that lets exactly-once
survive an operator-driven restart, a version upgrade, or a rescale.

## The Flink runtime port

The cluster sits behind the `FlinkRuntime` port (submit, stop-with-savepoint,
trigger-savepoint, cancel, status). Two adapters implement it:

- `InMemoryFlinkRuntime` is the default. It tracks job state in process, so the full stack
  and the entire test suite run without a Flink cluster.
- `FlinkRestRuntime` drives the Flink REST API. `build_job_config` translates a job into
  Flink pipeline configuration: it maps the delivery guarantee to
  `execution.checkpointing.mode`, sets the checkpoint interval, timeout, pause, and
  concurrency, encodes the restart strategy, wires the Iceberg sink connector, and restores
  from a savepoint path when one is present.

The adapter is chosen by configuration: set `CASCADE_FLINK_REST_URL` (with a job jar id) to
use a real cluster, leave it unset to stay in memory.

## Cross-context integrity

A job may reference a data contract for the schema it processes. When it does, the
application service checks the contract exists and rejects an unknown one, and the database
enforces it again with a nullable foreign key from `stream_jobs.contract_id` to
`data_contracts.id` (on delete set null, since a job can outlive a contract revision).

## Endpoints

| Method | Path                                      | Scope              |
| ------ | ----------------------------------------- | ------------------ |
| POST   | `/api/v1/jobs`                            | `processing:write` |
| GET    | `/api/v1/jobs`                            | `processing:read`  |
| GET    | `/api/v1/jobs/{id}`                       | `processing:read`  |
| POST   | `/api/v1/jobs/{id}/submit`                | `processing:write` |
| POST   | `/api/v1/jobs/{id}/suspend`               | `processing:write` |
| POST   | `/api/v1/jobs/{id}/resume`                | `processing:write` |
| POST   | `/api/v1/jobs/{id}/cancel`                | `processing:write` |
| POST   | `/api/v1/jobs/{id}/savepoints`            | `processing:write` |
| PUT    | `/api/v1/jobs/{id}/checkpoint-config`     | `processing:write` |

Definition is idempotent via the `Idempotency-Key` header. List supports filtering by
`status`, `sink_kind`, `delivery_guarantee`, and `contract_id`, with the usual pagination
and sort.
