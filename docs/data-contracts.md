# Data contracts and schema compatibility

A data contract is the governed, versioned description of the records flowing through a
dataset. Cascade treats it as a first-class aggregate so that a schema change cannot
silently break downstream consumers. Every new version is checked against the contract's
compatibility mode before it is accepted, and the check runs inside the domain rather than
in an external service, which keeps the rule authoritative and fully unit-testable.

## The aggregate

`DataContract` is the consistency boundary. It owns an ordered list of `SchemaVersion`
entities, a serialization format (Avro, Protobuf, or JSON Schema), a compatibility mode,
and a status. A contract always has at least one version: registration creates version 1.
Publishing appends the next monotonic version only after the candidate schema passes the
compatibility check against the latest published version. A deprecated contract rejects
further publishes.

## Schema model

A schema is an ordered set of fields. Each field has a name, a type, a nullability flag,
and a `has_default` flag. A field has an effective default when it is nullable or declares
a default; this is what makes adding or removing it safe in certain directions. Supported
field types are boolean, int, long, float, double, string, bytes, date, and timestamp.

## Compatibility modes

Compatibility is defined in terms of a reader schema reading data written with a writer
schema. Two ideas drive every rule: type promotion (a value written as one type can be
read as a wider type) and effective defaults (a reader can supply a value the writer did
not provide).

Promotions follow Avro's widening rules: int to long, float, or double; long to float or
double; float to double; string to and from bytes; and date to timestamp.

| Mode     | Meaning                                             | Safe changes |
| -------- | --------------------------------------------------- | ------------ |
| none     | No checking.                                        | Anything. |
| backward | The new schema can read data written with the old.  | Remove a field; add a field with a default; widen a type. |
| forward  | The old schema can read data written with the new.  | Add a field; remove a field that had a default. |
| full     | Both backward and forward hold.                     | Add or remove a field that has a default; widen a type. |

A rejected publish raises with the full list of violations. The API returns HTTP 409 with
`compatibility_mode` and a `violations` array so a caller can see exactly what broke.

## Schema registry integration

Publishing a version registers the schema with an external registry through the
`SchemaRegistry` port, and the returned id is stored on the version. Two adapters ship:

- `InMemorySchemaRegistry` (default): assigns monotonic ids with no external service, so
  the stack runs and tests pass out of the box.
- `ConfluentSchemaRegistry`: posts to a Confluent-compatible REST API. Enable it by setting
  `CASCADE_SCHEMA_REGISTRY_URL`.

The domain compatibility check is the authoritative gate; registration is a side effect
recorded for interoperability with the broader Kafka ecosystem.

## Endpoints

- `POST /api/v1/contracts` registers a contract with its first schema version.
- `POST /api/v1/contracts/{id}/versions` publishes a new version (compatibility enforced).
- `POST /api/v1/contracts/{id}/compatibility` is a dry run that reports compatibility
  without publishing.
- `PUT /api/v1/contracts/{id}/compatibility-mode` changes the mode.
- `POST /api/v1/contracts/{id}/versions/{version}/deprecate` and
  `POST /api/v1/contracts/{id}/deprecate` retire a version or the whole contract.
- `GET` variants read a contract, a single version, or a paginated list.

## Example

Register a contract, then evolve it safely by adding a defaulted field:

```bash
curl -X POST localhost:8000/api/v1/contracts \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{
    "name": "orders-value",
    "schema_format": "avro",
    "compatibility_mode": "backward",
    "schema": {"fields": [
      {"name": "id", "type": "long"},
      {"name": "amount", "type": "double"}
    ]}
  }'

curl -X POST localhost:8000/api/v1/contracts/<id>/versions \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"schema": {"fields": [
    {"name": "id", "type": "long"},
    {"name": "amount", "type": "double"},
    {"name": "currency", "type": "string", "has_default": true}
  ]}}'
```

Dropping the default on `currency` above would return 409 with a violation naming the
field, because a backward reader could not fill it when reading older records.
