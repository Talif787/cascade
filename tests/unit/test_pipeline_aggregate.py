from __future__ import annotations

import pytest

from cascade.domain.pipelines.aggregate import Pipeline
from cascade.domain.pipelines.errors import InvalidStateTransition
from cascade.domain.pipelines.events import PipelineRegistered, PipelineStatusChanged
from cascade.domain.pipelines.value_objects import (
    ConnectorType,
    PipelineName,
    PipelineStatus,
    SinkTarget,
    SinkType,
    SourceConnector,
)


def _new_pipeline() -> Pipeline:
    return Pipeline.register(
        name=PipelineName("orders-cdc"),
        source=SourceConnector(type=ConnectorType.POSTGRES_CDC, resource="public.orders"),
        sink=SinkTarget(type=SinkType.ICEBERG, resource="bronze.orders"),
        description="  demo  ",
    )


def test_register_starts_in_draft_and_records_event() -> None:
    pipeline = _new_pipeline()
    assert pipeline.status is PipelineStatus.DRAFT
    assert pipeline.description == "demo"
    events = pipeline.pull_events()
    assert any(isinstance(event, PipelineRegistered) for event in events)
    assert pipeline.pull_events() == []


def test_activate_from_draft_transitions_and_emits_event() -> None:
    pipeline = _new_pipeline()
    pipeline.pull_events()
    pipeline.activate()
    assert pipeline.status is PipelineStatus.ACTIVE
    change = pipeline.pull_events()[0]
    assert isinstance(change, PipelineStatusChanged)
    assert change.previous is PipelineStatus.DRAFT
    assert change.current is PipelineStatus.ACTIVE


def test_pause_requires_active_state() -> None:
    pipeline = _new_pipeline()
    with pytest.raises(InvalidStateTransition):
        pipeline.pause()


def test_archived_pipeline_is_terminal() -> None:
    pipeline = _new_pipeline()
    pipeline.archive()
    assert pipeline.status is PipelineStatus.ARCHIVED
    with pytest.raises(InvalidStateTransition):
        pipeline.activate()


def test_active_to_paused_to_active_cycle() -> None:
    pipeline = _new_pipeline()
    pipeline.activate()
    pipeline.pause()
    assert pipeline.status is PipelineStatus.PAUSED
    pipeline.activate()
    assert pipeline.status is PipelineStatus.ACTIVE
