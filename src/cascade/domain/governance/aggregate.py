from __future__ import annotations

from datetime import datetime

from cascade.domain.common.entity import AggregateRoot, utcnow
from cascade.domain.governance.errors import InvalidAssetRef, InvalidSloTransition
from cascade.domain.governance.events import (
    FreshnessEvaluated,
    FreshnessTargetChanged,
    SloBreached,
    SloRegistered,
    SloStatusChanged,
)
from cascade.domain.governance.value_objects import (
    AssetRef,
    ComplianceState,
    FreshnessTarget,
    Severity,
    SloId,
    SloName,
    SloStatus,
)

_MAX_DESCRIPTION_LEN = 1024

_ALLOWED_TRANSITIONS: dict[SloStatus, frozenset[SloStatus]] = {
    SloStatus.ACTIVE: frozenset({SloStatus.SUSPENDED, SloStatus.RETIRED}),
    SloStatus.SUSPENDED: frozenset({SloStatus.ACTIVE, SloStatus.RETIRED}),
    SloStatus.RETIRED: frozenset(),
}


class ServiceLevelObjective(AggregateRoot[SloId]):
    """A freshness SLA bound to a refreshable asset."""

    def __init__(
        self,
        slo_id: SloId,
        *,
        name: SloName,
        asset: AssetRef,
        target: FreshnessTarget,
        severity: Severity,
        owner: str,
        description: str,
        status: SloStatus,
        state: ComplianceState,
        last_evaluated_at: datetime | None,
        last_staleness_minutes: int | None,
        breach_count: int,
        created_at: datetime,
        updated_at: datetime,
        version: int = 0,
    ) -> None:
        super().__init__(slo_id, version=version)
        self._name = name
        self._asset = asset
        self._target = target
        self._severity = severity
        self._owner = owner
        self._description = description
        self._status = status
        self._state = state
        self._last_evaluated_at = last_evaluated_at
        self._last_staleness_minutes = last_staleness_minutes
        self._breach_count = breach_count
        self._created_at = created_at
        self._updated_at = updated_at

    @classmethod
    def register(
        cls,
        *,
        name: SloName,
        asset: AssetRef,
        target: FreshnessTarget,
        severity: Severity = Severity.MEDIUM,
        owner: str = "",
        description: str = "",
    ) -> ServiceLevelObjective:
        if not asset.is_refreshable:
            raise InvalidAssetRef(
                f"a freshness SLO can only target a refreshable asset, not {asset.kind.value}"
            )
        now = utcnow()
        slo = cls(
            SloId.new(),
            name=name,
            asset=asset,
            target=target,
            severity=severity,
            owner=owner.strip(),
            description=description.strip()[:_MAX_DESCRIPTION_LEN],
            status=SloStatus.ACTIVE,
            state=ComplianceState.UNKNOWN,
            last_evaluated_at=None,
            last_staleness_minutes=None,
            breach_count=0,
            created_at=now,
            updated_at=now,
        )
        slo._record(SloRegistered(slo_id=slo.id, name=str(name), asset=str(asset)))
        return slo

    @property
    def name(self) -> SloName:
        return self._name

    @property
    def asset(self) -> AssetRef:
        return self._asset

    @property
    def target(self) -> FreshnessTarget:
        return self._target

    @property
    def severity(self) -> Severity:
        return self._severity

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def description(self) -> str:
        return self._description

    @property
    def status(self) -> SloStatus:
        return self._status

    @property
    def state(self) -> ComplianceState:
        return self._state

    @property
    def last_evaluated_at(self) -> datetime | None:
        return self._last_evaluated_at

    @property
    def last_staleness_minutes(self) -> int | None:
        return self._last_staleness_minutes

    @property
    def breach_count(self) -> int:
        return self._breach_count

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def evaluate(self, last_refresh_at: datetime | None, now: datetime) -> ComplianceState:
        if self._status is not SloStatus.ACTIVE:
            return self._state
        staleness_minutes = self._staleness_minutes(last_refresh_at, now)
        state = self._classify(staleness_minutes)
        previously_breached = self._state is ComplianceState.BREACHED
        self._state = state
        self._last_staleness_minutes = staleness_minutes
        self._last_evaluated_at = now
        self._updated_at = now
        self._record(
            FreshnessEvaluated(slo_id=self.id, state=state, staleness_minutes=staleness_minutes)
        )
        if state is ComplianceState.BREACHED and not previously_breached:
            self._breach_count += 1
            self._record(SloBreached(slo_id=self.id, staleness_minutes=staleness_minutes))
        return state

    def change_target(self, target: FreshnessTarget) -> None:
        self._target = target
        self._updated_at = utcnow()
        self._record(
            FreshnessTargetChanged(
                slo_id=self.id, max_staleness_minutes=target.max_staleness_minutes
            )
        )

    def suspend(self) -> None:
        self._transition_to(SloStatus.SUSPENDED)

    def resume(self) -> None:
        self._transition_to(SloStatus.ACTIVE)

    def retire(self) -> None:
        self._transition_to(SloStatus.RETIRED)

    def _staleness_minutes(self, last_refresh_at: datetime | None, now: datetime) -> int:
        if last_refresh_at is None:
            return self._target.max_staleness_minutes * 1000
        delta = now - last_refresh_at
        return max(0, int(delta.total_seconds() // 60))

    def _classify(self, staleness_minutes: int) -> ComplianceState:
        if staleness_minutes > self._target.max_staleness_minutes:
            return ComplianceState.BREACHED
        if staleness_minutes >= self._target.warn_threshold_minutes:
            return ComplianceState.AT_RISK
        return ComplianceState.MEETING

    def _transition_to(self, target: SloStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self._status]:
            raise InvalidSloTransition(self._status.value, target.value)
        previous = self._status
        self._status = target
        self._updated_at = utcnow()
        self._record(SloStatusChanged(slo_id=self.id, previous=previous, current=target))
