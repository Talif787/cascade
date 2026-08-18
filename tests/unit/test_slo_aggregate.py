from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cascade.domain.governance.aggregate import ServiceLevelObjective
from cascade.domain.governance.errors import InvalidAssetRef, InvalidSloTransition
from cascade.domain.governance.events import (
    FreshnessEvaluated,
    SloBreached,
    SloRegistered,
)
from cascade.domain.governance.value_objects import (
    AssetKind,
    AssetRef,
    ComplianceState,
    FreshnessTarget,
    Severity,
    SloName,
    SloStatus,
)


def _slo(
    *,
    kind: AssetKind = AssetKind.DATASET,
    minutes: int = 60,
) -> ServiceLevelObjective:
    return ServiceLevelObjective.register(
        name=SloName("orders-freshness"),
        asset=AssetRef(kind=kind, asset_id="asset-1"),
        target=FreshnessTarget(max_staleness_minutes=minutes),
        severity=Severity.HIGH,
    )


def test_register_starts_active_and_unknown() -> None:
    slo = _slo()
    assert slo.status is SloStatus.ACTIVE
    assert slo.state is ComplianceState.UNKNOWN
    assert any(isinstance(e, SloRegistered) for e in slo.pull_events())


def test_freshness_slo_requires_refreshable_asset() -> None:
    with pytest.raises(InvalidAssetRef):
        ServiceLevelObjective.register(
            name=SloName("bad"),
            asset=AssetRef(kind=AssetKind.PIPELINE, asset_id="p1"),
            target=FreshnessTarget(max_staleness_minutes=60),
        )


def test_serving_view_asset_is_allowed() -> None:
    slo = _slo(kind=AssetKind.SERVING_VIEW)
    assert slo.asset.kind is AssetKind.SERVING_VIEW


def test_evaluate_meeting_when_fresh() -> None:
    slo = _slo(minutes=60)
    slo.pull_events()
    now = datetime.now(UTC)
    state = slo.evaluate(now - timedelta(minutes=10), now)
    assert state is ComplianceState.MEETING
    assert slo.last_staleness_minutes == 10
    assert any(isinstance(e, FreshnessEvaluated) for e in slo.pull_events())


def test_evaluate_at_risk_near_threshold() -> None:
    slo = _slo(minutes=60)
    now = datetime.now(UTC)
    # 80% of 60 is 48 minutes; 50 minutes is at risk but not breached
    state = slo.evaluate(now - timedelta(minutes=50), now)
    assert state is ComplianceState.AT_RISK


def test_evaluate_breached_when_stale() -> None:
    slo = _slo(minutes=60)
    now = datetime.now(UTC)
    state = slo.evaluate(now - timedelta(minutes=120), now)
    assert state is ComplianceState.BREACHED
    assert slo.breach_count == 1
    assert any(isinstance(e, SloBreached) for e in slo.pull_events())


def test_never_refreshed_is_breached() -> None:
    slo = _slo(minutes=60)
    state = slo.evaluate(None, datetime.now(UTC))
    assert state is ComplianceState.BREACHED


def test_breach_count_only_increments_on_new_breach() -> None:
    slo = _slo(minutes=60)
    now = datetime.now(UTC)
    slo.evaluate(now - timedelta(minutes=120), now)
    slo.evaluate(now - timedelta(minutes=130), now)
    assert slo.breach_count == 1
    # recover then breach again -> counts a second time
    slo.evaluate(now - timedelta(minutes=1), now)
    slo.evaluate(now - timedelta(minutes=200), now)
    assert slo.breach_count == 2


def test_suspended_slo_is_not_evaluated() -> None:
    slo = _slo(minutes=60)
    slo.suspend()
    now = datetime.now(UTC)
    state = slo.evaluate(now - timedelta(minutes=999), now)
    assert state is ComplianceState.UNKNOWN


def test_lifecycle_suspend_resume_retire() -> None:
    slo = _slo()
    slo.suspend()
    assert slo.status is SloStatus.SUSPENDED
    slo.resume()
    assert slo.status is SloStatus.ACTIVE
    slo.retire()
    assert slo.status is SloStatus.RETIRED
    with pytest.raises(InvalidSloTransition):
        slo.resume()


def test_change_target() -> None:
    slo = _slo(minutes=60)
    slo.pull_events()
    slo.change_target(FreshnessTarget(max_staleness_minutes=30))
    assert slo.target.max_staleness_minutes == 30
