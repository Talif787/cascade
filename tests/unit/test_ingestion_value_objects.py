from __future__ import annotations

import pytest

from cascade.domain.ingestion.errors import (
    InvalidConnectorConfig,
    InvalidDeadLetterPolicy,
    InvalidSourceId,
    InvalidSourceName,
)
from cascade.domain.ingestion.value_objects import (
    ConnectorConfig,
    DeadLetterPolicy,
    FailureAction,
    IngestionSourceId,
    SourceName,
)


@pytest.mark.parametrize("value", ["orders-cdc", "a12", "postgres-source-1"])
def test_valid_source_names(value: str) -> None:
    assert str(SourceName(value)) == value


@pytest.mark.parametrize("value", ["", "ab", "Orders", "1source", "has space", "x" * 64])
def test_invalid_source_names(value: str) -> None:
    with pytest.raises(InvalidSourceName):
        SourceName(value)


def test_source_id_round_trip() -> None:
    identity = IngestionSourceId.new()
    assert IngestionSourceId.from_string(str(identity)) == identity


def test_source_id_rejects_non_uuid() -> None:
    with pytest.raises(InvalidSourceId):
        IngestionSourceId.from_string("not-a-uuid")


def test_connector_config_rejects_non_string_values() -> None:
    with pytest.raises(InvalidConnectorConfig):
        ConnectorConfig(options={"tasks.max": 3})  # type: ignore[dict-item]


def test_connector_config_is_immutable_copy() -> None:
    raw = {"database.hostname": "db"}
    config = ConnectorConfig(options=raw)
    raw["database.hostname"] = "other"
    assert config.as_dict() == {"database.hostname": "db"}


def test_dead_letter_policy_requires_topic_for_dead_letter_action() -> None:
    with pytest.raises(InvalidDeadLetterPolicy):
        DeadLetterPolicy(on_failure=FailureAction.DEAD_LETTER, dlq_topic=None)


def test_dead_letter_policy_rejects_negative_values() -> None:
    with pytest.raises(InvalidDeadLetterPolicy):
        DeadLetterPolicy(on_failure=FailureAction.SKIP, max_retries=-1)
    with pytest.raises(InvalidDeadLetterPolicy):
        DeadLetterPolicy(on_failure=FailureAction.SKIP, tolerance=-1)


def test_halt_policy_allows_missing_topic() -> None:
    policy = DeadLetterPolicy(on_failure=FailureAction.HALT, tolerance=5)
    assert policy.trips_on_breach is True
