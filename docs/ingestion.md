# Ingestion sources and connector runtime

The ingestion context is where the control plane manages the connectors that pull data
out of external systems and into the platform. Cascade does not move the bytes itself:
that is the data plane's job, handled by Kafka Connect and Debezium. What the control
plane owns is the governed description of each source, its lifecycle, and the policy that
decides what happens when records fail. Keeping that authority in one place is what lets
the platform enforce a data contract at the point of ingestion rather than discovering a
break three hops downstream.

## The IngestionSource aggregate

`IngestionSource` is the consistency boundary. It holds a connector kind, a validated
connector configuration, the id of the data contract that governs the records it produces,
an optional pipeline it feeds, a dead-letter policy, a running dead-letter count, and a
reference to the connector once the runtime has accepted it. Registration always starts a
source in the `registered` state; nothing is deployed until it is explicitly provisioned.

The lifecycle is a small, explicit state machine. Illegal moves raise
`InvalidSourceTransition` inside the domain, so the rule is authoritative and unit-testable
rather than scattered across handlers.

```
registered     -> provisioning, decommissioned
provisioning   -> running, failed, decommissioned
running        -> paused, failed, decommissioned
paused         -> running, decommissioned
failed         -> provisioning, decommissioned
decommissioned -> (terminal)
```

Provisioning is deliberately two-step: the aggregate moves to `provisioning`, the
application service asks the runtime to deploy the connector, and only a successful deploy
moves the source to `running` and records the runtime reference. A failed deploy moves the
source to `failed` and surfaces a conflict, so the stored state always matches what the
runtime actually did.

## Dead-letter policy and breach behaviour

A `DeadLetterPolicy` combines a failure action (`dead_letter`, `skip`, or `halt`), an
optional dead-letter topic, a retry budget, and a tolerance. Tolerance is the number of
failed records that trips a breach; a tolerance of zero means the source never halts on
dead letters and simply accumulates the count. When a breach trips, the aggregate always
records a `DeadLetterThresholdBreached` event, and if the policy's action is `halt` the
source transitions to `failed`. The application service then pauses the underlying
connector so a halted source stops consuming. A `dead_letter` policy requires a topic,
which is validated when the policy is built.

## The connector runtime port

The external runtime sits behind the `ConnectorRuntime` port (deploy, pause, resume,
delete, status). Two adapters implement it:

- `InMemoryConnectorRuntime` is the default. It tracks connector state in process, so the
  full stack and the entire test suite run without a Kafka cluster.
- `KafkaConnectRuntime` talks to the Kafka Connect REST API. `build_connector_config`
  translates a source into a Connect config document: it maps the connector kind to the
  right Debezium connector class (for example the Postgres CDC kind becomes
  `io.debezium.connector.postgresql.PostgresConnector`) and folds the dead-letter policy
  into Connect's own error-handling settings (`errors.tolerance`,
  `errors.deadletterqueue.topic.name`, and the retry timeout).

The adapter is chosen by configuration: set `CASCADE_KAFKA_CONNECT_URL` to use a real
cluster, leave it unset to stay in memory.

## Cross-context integrity

A source must reference a data contract that exists. The application service checks this at
registration and rejects an unknown contract with a validation error, and the database
enforces it again with a foreign key from `ingestion_sources.contract_id` to
`data_contracts.id` (on delete restrict). An optional pipeline reference is validated the
same way, with a nullable foreign key that is set null if the pipeline is later removed.

## Producer SDK

`cascade.sdk` is a standalone client that a data-plane producer uses to enforce a contract
before it produces a record. It depends only on httpx and the standard library, so it can
be vendored into a producer without pulling in the control-plane server. It resolves a
contract by id or by name, picks the latest published version, and validates a record
against that schema, returning the registry id the producer should attach to the message.

```python
from cascade.sdk import CascadeProducerClient

client = CascadeProducerClient("https://cascade.internal", token=token)
schema = await client.validate_record(contract_id, {"id": 1, "amount": 9.5})
# schema.registry_id is the id to embed alongside the produced record
```

Validation mirrors the contract's field model: it checks for missing required fields,
nulls in non-nullable fields, type mismatches, and fields that the contract does not
declare.

## Endpoints

| Method | Path                                        | Scope             |
| ------ | ------------------------------------------- | ----------------- |
| POST   | `/api/v1/sources`                           | `ingestion:write` |
| GET    | `/api/v1/sources`                           | `ingestion:read`  |
| GET    | `/api/v1/sources/{id}`                      | `ingestion:read`  |
| POST   | `/api/v1/sources/{id}/provision`            | `ingestion:write` |
| POST   | `/api/v1/sources/{id}/pause`                | `ingestion:write` |
| POST   | `/api/v1/sources/{id}/resume`               | `ingestion:write` |
| POST   | `/api/v1/sources/{id}/decommission`         | `ingestion:write` |
| POST   | `/api/v1/sources/{id}/dead-letters`         | `ingestion:write` |
| PUT    | `/api/v1/sources/{id}/dead-letter-policy`   | `ingestion:write` |

Registration is idempotent via the `Idempotency-Key` header. List supports filtering by
`status`, `connector_kind`, and `contract_id`, with the usual pagination and sort.
