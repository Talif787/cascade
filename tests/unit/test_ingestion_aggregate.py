from __future__ import annotations

import pytest

from cascade.domain.contracts.value_objects import DataContractId
from cascade.domain.ingestion.aggregate import IngestionSource
from cascade.domain.ingestion.errors import InvalidSourceTransition
from cascade.domain.ingestion.events import (
    DeadLetterThresholdBreached,
    IngestionSourceRegistered,
    SourceProvisioned,
)
from cascade.domain.ingestion.value_objects import (
    ConnectorConfig,
    ConnectorKind,
    DeadLetterPolicy,
    FailureAction,
    SourceName,
    SourceStatus,
)


def _source(policy: DeadLetterPolicy | None = None) -> IngestionSource:
    return IngestionSource.register(
        name=SourceName("orders-postgres-cdc"),
        connector_kind=ConnectorKind.POSTGRES_CDC,
        config=ConnectorConfig(options={"database.hostname": "db"}),
        contract_id=DataContractId.new(),
        dead_letter_policy=policy
        or DeadLetterPolicy(on_failure=FailureAction.DEAD_LETTER, dlq_topic="orders.dlq"),
    )


def test_register_starts_in_registered_state() -> None:
    source = _source()
    assert source.status is SourceStatus.REGISTERED
    assert any(isinstance(e, IngestionSourceRegistered) for e in source.pull_events())


def test_provision_lifecycle_emits_provisioned_once() -> None:
    source = _source()
    source.pull_events()
    source.begin_provisioning()
    assert source.status is SourceStatus.PROVISIONING
    source.mark_running("cascade.postgres_cdc.orders")
    assert source.status is SourceStatus.RUNNING
    assert source.runtime_ref == "cascade.postgres_cdc.orders"
    events = source.pull_events()
    assert sum(isinstance(e, SourceProvisioned) for e in events) == 1


def test_pause_and_resume() -> None:
    source = _source()
    source.begin_provisioning()
    source.mark_running("ref")
    source.pull_events()
    source.pause()
    assert source.status is SourceStatus.PAUSED
    source.resume()
    assert source.status is SourceStatus.RUNNING


def test_illegal_transition_raises() -> None:
    source = _source()
    with pytest.raises(InvalidSourceTransition):
        source.pause()  # cannot pause a source that was never running


def test_decommission_is_terminal() -> None:
    source = _source()
    source.decommission()
    assert source.status is SourceStatus.DECOMMISSIONED
    with pytest.raises(InvalidSourceTransition):
        source.begin_provisioning()


def test_dead_letters_accumulate_without_breach_when_tolerance_zero() -> None:
    source = _source()
    source.begin_provisioning()
    source.mark_running("ref")
    source.pull_events()
    source.record_dead_letters(5)
    assert source.dead_letter_count == 5
    assert source.status is SourceStatus.RUNNING
    assert not any(isinstance(e, DeadLetterThresholdBreached) for e in source.pull_events())


def test_dead_letter_breach_halts_when_policy_is_halt() -> None:
    policy = DeadLetterPolicy(on_failure=FailureAction.HALT, tolerance=3)
    source = _source(policy)
    source.begin_provisioning()
    source.mark_running("ref")
    source.pull_events()
    source.record_dead_letters(3)
    events = source.pull_events()
    assert any(isinstance(e, DeadLetterThresholdBreached) for e in events)
    assert source.status is SourceStatus.FAILED


def test_dead_letter_breach_without_halt_stays_running() -> None:
    policy = DeadLetterPolicy(on_failure=FailureAction.DEAD_LETTER, dlq_topic="dlq", tolerance=2)
    source = _source(policy)
    source.begin_provisioning()
    source.mark_running("ref")
    source.pull_events()
    source.record_dead_letters(2)
    events = source.pull_events()
    assert any(isinstance(e, DeadLetterThresholdBreached) for e in events)
    assert source.status is SourceStatus.RUNNING


def test_failed_source_can_be_reprovisioned() -> None:
    source = _source()
    source.begin_provisioning()
    source.mark_failed()
    assert source.status is SourceStatus.FAILED
    source.begin_provisioning()
    assert source.status is SourceStatus.PROVISIONING
