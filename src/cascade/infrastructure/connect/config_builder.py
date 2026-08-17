from __future__ import annotations

from cascade.application.ingestion.runtime import ConnectorSpec
from cascade.domain.ingestion.value_objects import (
    ConnectorKind,
    DeadLetterPolicy,
    FailureAction,
)

_CONNECTOR_CLASS: dict[ConnectorKind, str] = {
    ConnectorKind.POSTGRES_CDC: "io.debezium.connector.postgresql.PostgresConnector",
    ConnectorKind.MYSQL_CDC: "io.debezium.connector.mysql.MySqlConnector",
    ConnectorKind.MONGODB_CDC: "io.debezium.connector.mongodb.MongoDbConnector",
    ConnectorKind.KAFKA_TOPIC: "org.apache.kafka.connect.mirror.MirrorSourceConnector",
    ConnectorKind.HTTP_POLL: "com.github.castorm.kafka.connect.http.HttpSourceConnector",
    ConnectorKind.S3_OBJECT: "io.confluent.connect.s3.source.S3SourceConnector",
}


def _dead_letter_settings(policy: DeadLetterPolicy) -> dict[str, str]:
    if policy.on_failure is FailureAction.HALT:
        return {"errors.tolerance": "none"}
    settings: dict[str, str] = {
        "errors.tolerance": "all",
        "errors.retry.timeout": str(policy.max_retries),
    }
    if policy.on_failure is FailureAction.DEAD_LETTER and policy.dlq_topic:
        settings["errors.deadletterqueue.topic.name"] = policy.dlq_topic
        settings["errors.deadletterqueue.context.headers.enable"] = "true"
    return settings


def build_connector_config(spec: ConnectorSpec) -> dict[str, str]:
    config: dict[str, str] = {"connector.class": _CONNECTOR_CLASS[spec.kind]}
    config.update(spec.config.as_dict())
    config.update(_dead_letter_settings(spec.dead_letter_policy))
    config.setdefault("name", spec.name)
    return config
