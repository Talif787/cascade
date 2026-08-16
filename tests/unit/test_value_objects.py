from __future__ import annotations

import uuid

import pytest

from cascade.domain.pipelines.errors import (
    InvalidConnectorConfig,
    InvalidPipelineId,
    InvalidPipelineName,
)
from cascade.domain.pipelines.value_objects import (
    ConnectorType,
    PipelineId,
    PipelineName,
    SourceConnector,
)


@pytest.mark.parametrize("value", ["orders-cdc", "abc", "a" + "b" * 62])
def test_valid_pipeline_names(value: str) -> None:
    assert str(PipelineName(value)) == value


@pytest.mark.parametrize("value", ["", "ab", "Orders", "1pipeline", "has space", "a" * 64])
def test_invalid_pipeline_names_are_rejected(value: str) -> None:
    with pytest.raises(InvalidPipelineName):
        PipelineName(value)


def test_pipeline_id_round_trips_through_string() -> None:
    identifier = PipelineId.new()
    assert PipelineId.from_string(str(identifier)) == identifier


def test_pipeline_id_rejects_non_uuid() -> None:
    with pytest.raises(InvalidPipelineId):
        PipelineId.from_string("not-a-uuid")


def test_pipeline_id_equality_is_value_based() -> None:
    raw = uuid.uuid4()
    assert PipelineId(raw) == PipelineId(raw)


def test_source_connector_requires_resource() -> None:
    with pytest.raises(InvalidConnectorConfig):
        SourceConnector(type=ConnectorType.KAFKA_TOPIC, resource="   ")


def test_source_connector_options_are_immutable() -> None:
    connector = SourceConnector(
        type=ConnectorType.KAFKA_TOPIC, resource="events", options={"acks": "all"}
    )
    with pytest.raises(TypeError):
        connector.options["acks"] = "none"  # type: ignore[index]
