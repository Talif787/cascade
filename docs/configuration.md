# Configuration

All configuration is read from environment variables (twelve-factor). Variables use
the `CASCADE_` prefix and can also be placed in a `.env` file for local development.

| Variable                              | Default                                   | Description                                        |
| ------------------------------------- | ----------------------------------------- | -------------------------------------------------- |
| `CASCADE_ENVIRONMENT`                 | `local`                                   | `local`, `development`, `staging`, `production`.   |
| `CASCADE_LOG_LEVEL`                   | `INFO`                                    | Log level.                                         |
| `CASCADE_LOG_JSON`                    | `true`                                    | JSON logs when true, console renderer when false.  |
| `CASCADE_HTTP_HOST`                   | `0.0.0.0`                                 | Bind host.                                         |
| `CASCADE_HTTP_PORT`                   | `8000`                                    | Bind port.                                         |
| `CASCADE_ROOT_PATH`                   | empty                                     | ASGI root path when served behind a proxy prefix.  |
| `CASCADE_DATABASE_URL`                | local Postgres DSN                        | Async SQLAlchemy DSN (`postgresql+asyncpg://...`). |
| `CASCADE_DATABASE_POOL_SIZE`          | `10`                                      | Connection pool size.                              |
| `CASCADE_DATABASE_MAX_OVERFLOW`       | `20`                                      | Overflow connections beyond the pool.              |
| `CASCADE_DATABASE_POOL_TIMEOUT`       | `30`                                      | Seconds to wait for a pooled connection.           |
| `CASCADE_REDIS_URL`                   | `redis://localhost:6379/0`                | Redis DSN.                                         |
| `CASCADE_SCHEMA_REGISTRY_URL`         | empty                                     | Confluent-compatible registry URL; empty uses the in-memory adapter. |
| `CASCADE_DEFAULT_COMPATIBILITY_MODE`  | `backward`                                | Default compatibility mode for new contracts.      |
| `CASCADE_KAFKA_CONNECT_URL`           | empty                                     | Kafka Connect REST URL for the ingestion runtime; empty uses the in-memory adapter. |
| `CASCADE_FLINK_REST_URL`              | empty                                     | Flink cluster REST URL for the processing runtime; empty uses the in-memory adapter. |
| `CASCADE_FLINK_JAR_ID`                | empty                                     | Uploaded job jar id used when submitting Flink jobs. Required alongside the REST URL. |
| `CASCADE_FLINK_ENTRY_CLASS`           | empty                                     | Optional entry class for the Flink job jar.        |
| `CASCADE_DBT_CLOUD_API_URL`           | empty                                     | dbt Cloud API URL for the transformation runtime; empty uses the in-memory adapter. |
| `CASCADE_DBT_CLOUD_ACCOUNT_ID`        | empty                                     | dbt Cloud account id. Required alongside the API URL. |
| `CASCADE_DBT_CLOUD_JOB_ID`            | empty                                     | dbt Cloud job id triggered on materialize. Required alongside the API URL. |
| `CASCADE_DBT_CLOUD_TOKEN`             | empty                                     | dbt Cloud API token. Required alongside the API URL. |
| `CASCADE_AIRFLOW_API_URL`             | empty                                     | Airflow REST URL for the orchestrator; empty uses the in-memory adapter. |
| `CASCADE_AIRFLOW_USERNAME`            | empty                                     | Airflow basic-auth username. Required alongside the API URL. |
| `CASCADE_AIRFLOW_PASSWORD`            | empty                                     | Airflow basic-auth password. Required alongside the API URL. |
| `CASCADE_AUTH_ENABLED`                | `true`                                    | When false, all requests are treated as authorized (local only). |
| `CASCADE_JWT_ALGORITHM`               | `HS256`                                   | Signing algorithm.                                 |
| `CASCADE_JWT_SECRET`                  | `change-me-in-production`                 | HS256 shared secret.                               |
| `CASCADE_JWT_JWKS_URL`                | empty                                     | JWKS endpoint for RS256/OIDC verification.         |
| `CASCADE_JWT_ISSUER`                  | empty                                     | Expected `iss` claim.                              |
| `CASCADE_JWT_AUDIENCE`                | empty                                     | Expected `aud` claim.                              |
| `CASCADE_RATE_LIMIT_ENABLED`          | `true`                                    | Enable the rate-limit middleware.                  |
| `CASCADE_RATE_LIMIT_PER_MINUTE`       | `120`                                     | Sustained request rate per client.                 |
| `CASCADE_RATE_LIMIT_BURST`            | `40`                                      | Token bucket capacity.                             |
| `CASCADE_OTEL_ENABLED`                | `false`                                   | Enable OpenTelemetry tracing.                      |
| `CASCADE_OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318`                   | OTLP/HTTP collector base URL.                      |
| `CASCADE_IDEMPOTENCY_TTL_SECONDS`     | `86400`                                   | Retention for idempotency keys.                    |
| `CASCADE_CACHE_TTL_SECONDS`           | `60`                                      | Default cache TTL.                                 |

## Production notes

- Set `CASCADE_AUTH_ENABLED=true` and configure `CASCADE_JWT_JWKS_URL`,
  `CASCADE_JWT_ISSUER`, and `CASCADE_JWT_AUDIENCE` to verify tokens against your
  identity provider. Do not rely on the HS256 secret outside development.
- Secrets (`CASCADE_JWT_SECRET`, database credentials) are injected from your secret
  manager, never committed. Kubernetes secret templating arrives in Phase 9.
- Tune `CASCADE_DATABASE_POOL_SIZE` to your instance connection budget.
