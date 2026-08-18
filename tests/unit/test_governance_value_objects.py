from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cascade.domain.governance.aggregate_cost import CostEntry
from cascade.domain.governance.errors import (
    InvalidAssetRef,
    InvalidCostPeriod,
    InvalidFreshnessTarget,
    InvalidMoney,
    InvalidSloId,
    InvalidSloName,
)
from cascade.domain.governance.value_objects import (
    AssetKind,
    AssetRef,
    CostCategory,
    CostPeriod,
    FreshnessTarget,
    Money,
    SloId,
    SloName,
)


@pytest.mark.parametrize("value", ["orders-freshness", "a1", "gold-daily-sla"])
def test_valid_slo_names(value: str) -> None:
    assert str(SloName(value)) == value


@pytest.mark.parametrize("value", ["", "A", "x", "has space", "UPPER"])
def test_invalid_slo_names(value: str) -> None:
    with pytest.raises(InvalidSloName):
        SloName(value)


def test_slo_id_round_trip() -> None:
    identity = SloId.new()
    assert SloId.from_string(str(identity)) == identity


def test_slo_id_rejects_non_uuid() -> None:
    with pytest.raises(InvalidSloId):
        SloId.from_string("nope")


def test_asset_ref_requires_id() -> None:
    with pytest.raises(InvalidAssetRef):
        AssetRef(kind=AssetKind.DATASET, asset_id="  ")


def test_asset_ref_refreshable_flag() -> None:
    assert AssetRef(kind=AssetKind.DATASET, asset_id="x").is_refreshable is True
    assert AssetRef(kind=AssetKind.SERVING_VIEW, asset_id="x").is_refreshable is True
    assert AssetRef(kind=AssetKind.PIPELINE, asset_id="x").is_refreshable is False


def test_freshness_target_must_be_positive() -> None:
    with pytest.raises(InvalidFreshnessTarget):
        FreshnessTarget(max_staleness_minutes=0)


def test_freshness_warn_threshold() -> None:
    assert FreshnessTarget(max_staleness_minutes=100).warn_threshold_minutes == 80.0


def test_money_rejects_negative() -> None:
    with pytest.raises(InvalidMoney):
        Money(amount_cents=-1)


def test_money_rejects_bad_currency() -> None:
    with pytest.raises(InvalidMoney):
        Money(amount_cents=100, currency="US")


def test_money_add_same_currency() -> None:
    total = Money(amount_cents=100).add(Money(amount_cents=250))
    assert total.amount_cents == 350


def test_money_add_different_currency_fails() -> None:
    with pytest.raises(InvalidMoney):
        Money(amount_cents=100, currency="USD").add(Money(amount_cents=1, currency="EUR"))


def test_cost_period_must_be_ordered() -> None:
    now = datetime.now(UTC)
    with pytest.raises(InvalidCostPeriod):
        CostPeriod(start=now, end=now)


def test_cost_entry_records_event() -> None:
    now = datetime.now(UTC)
    entry = CostEntry.record(
        asset=AssetRef(kind=AssetKind.DATASET, asset_id="d1"),
        category=CostCategory.COMPUTE,
        amount=Money(amount_cents=1234),
        period=CostPeriod(start=now - timedelta(days=1), end=now),
    )
    assert entry.amount.amount_cents == 1234
    assert entry.category is CostCategory.COMPUTE
    assert entry.pull_events()
