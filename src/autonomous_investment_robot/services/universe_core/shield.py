from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .execution import ExecutionPlan
from .mission import MissionDecision
from .parliament import ParliamentVerdict
from .state import WorldStateSnapshot


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _dedupe_codes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        name = str(code or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


class ShieldEscalationState(str, Enum):
    NORMAL = "normal"
    CAUTIOUS = "cautious"
    DEFENSIVE = "defensive"
    OBSERVE_ONLY = "observe_only"
    HARD_STOP = "hard_stop"


class ShieldEscalationReason(str, Enum):
    NORMAL_BASELINE = "normal_baseline"
    META_DIAGNOSTICS_DEGRADED = "meta_diagnostics_degraded"
    META_DIAGNOSTICS_UNAVAILABLE = "meta_diagnostics_unavailable"
    STRATEGY_HEALTH_WEAKENING = "strategy_health_weakening"
    EXECUTION_STRESS_RISING = "execution_stress_rising"
    REGIME_CONFIDENCE_WEAKENING = "regime_confidence_weakening"
    EXECUTION_INFRA_ACCOUNT_COMPOUND_STRESS = "execution_infra_account_compound_stress"
    MULTI_STRATEGY_DECAY = "multi_strategy_decay"
    PORTFOLIO_STRESS_DEFENSIVE = "portfolio_stress_defensive"
    CONFIDENCE_COLLAPSE = "confidence_collapse"
    EXPLORATION_BUDGET_UNSAFE = "exploration_budget_unsafe"
    NO_TRADE_CONVERGENCE = "no_trade_convergence"
    STALE_OR_DEGRADED_DATA = "stale_or_degraded_data"
    CRITICAL_MULTI_FACTOR_FAILURE = "critical_multi_factor_failure"
    EXECUTION_INFRA_FAILURE_STACK = "execution_infra_failure_stack"
    HARD_SAFETY_DOCTRINE = "hard_safety_doctrine"
    HYSTERESIS_HOLD = "hysteresis_hold"
    SUSTAINED_RECOVERY = "sustained_recovery"


_STATE_SEQUENCE: tuple[ShieldEscalationState, ...] = (
    ShieldEscalationState.NORMAL,
    ShieldEscalationState.CAUTIOUS,
    ShieldEscalationState.DEFENSIVE,
    ShieldEscalationState.OBSERVE_ONLY,
    ShieldEscalationState.HARD_STOP,
)
_STATE_ORDER = {state: idx for idx, state in enumerate(_STATE_SEQUENCE)}


@dataclass(frozen=True)
class ShieldOverrideRecord:
    applied: bool = False
    override_type: str = ""
    reason: str = ""
    no_trade_forced: bool = False
    hard_stop_forced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": bool(self.applied),
            "override_type": self.override_type,
            "reason": self.reason,
            "no_trade_forced": bool(self.no_trade_forced),
            "hard_stop_forced": bool(self.hard_stop_forced),
        }


@dataclass(frozen=True)
class ShieldHysteresisState:
    active_state: ShieldEscalationState = ShieldEscalationState.NORMAL
    candidate_state: ShieldEscalationState = ShieldEscalationState.NORMAL
    recovery_streak: int = 0
    hold_count: int = 0
    transitions: int = 0
    decisions: int = 0
    last_reason_codes: tuple[str, ...] = field(default_factory=tuple)
    last_cycle_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_state": self.active_state.value,
            "candidate_state": self.candidate_state.value,
            "recovery_streak": int(self.recovery_streak),
            "hold_count": int(self.hold_count),
            "transitions": int(self.transitions),
            "decisions": int(self.decisions),
            "last_reason_codes": list(self.last_reason_codes),
            "last_cycle_id": self.last_cycle_id,
        }


@dataclass(frozen=True)
class ShieldHealthEnvelope:
    mission: str
    mission_confidence: float
    mission_no_trade_preferred: bool
    mission_allow_new_risk: bool
    parliament_no_trade: bool
    parliament_mode: str
    parliament_top_score: float
    parliament_selected_count: int
    strategy_health_score: float
    weak_strategy_signals: int
    strategy_health_vector: list[dict[str, Any]]
    adaptive_allocation_vector: list[dict[str, Any]]
    regime_cluster: str
    regime_confidence: float
    exploration_budget: float
    exploitation_budget: float
    meta_risk_scale: float
    meta_available: bool
    effective_confidence: float
    execution_stress: float
    slippage_stress: float
    infra_degradation: float
    stale_feed: bool
    desync: bool
    world_state_available: bool
    critical_stale_domains: list[str]
    drawdown_pct: float
    account_stress: float
    risk_mode: str
    risk_hard_stop: bool
    risk_observe_only: bool
    risk_flags: list[str]
    plan_actionable: bool
    plan_side: str

    @classmethod
    def from_inputs(
        cls,
        *,
        world: WorldStateSnapshot,
        mission: MissionDecision,
        verdict: ParliamentVerdict,
        plan: ExecutionPlan,
        meta_diagnostics: Mapping[str, Any] | Any | None,
    ) -> "ShieldHealthEnvelope":
        meta_payload: dict[str, Any]
        if meta_diagnostics is None:
            meta_payload = {}
        elif isinstance(meta_diagnostics, Mapping):
            meta_payload = dict(meta_diagnostics)
        elif hasattr(meta_diagnostics, "to_dict"):
            try:
                raw = meta_diagnostics.to_dict()
                meta_payload = dict(raw) if isinstance(raw, Mapping) else {}
            except Exception:
                meta_payload = {}
        else:
            meta_payload = {}

        ranked = list(verdict.ranking)
        ranked_active = [row for row in ranked if row.proposal.strategy != "no_trade_guardian"][:5]
        health_vector: list[dict[str, Any]] = []
        weak = 0
        scores: list[float] = []
        for row in ranked_active:
            composite = _safe_float(row.diagnostics.get("composite_score", row.score), row.score)
            confidence = _safe_float(row.proposal.confidence, 0.0)
            regime_fit = _safe_float(row.proposal.regime_compatibility, 0.0)
            if composite < 0.55 or confidence < 0.45 or regime_fit < 0.40:
                weak += 1
            scores.append(max(0.0, composite))
            health_vector.append(
                {
                    "strategy": row.proposal.strategy,
                    "score": float(row.score),
                    "composite_score": float(composite),
                    "confidence": float(confidence),
                    "regime_compatibility": float(regime_fit),
                }
            )

        top_score = float(scores[0]) if scores else 0.0
        avg_score = sum(scores) / max(len(scores), 1)
        strategy_health = _clamp((top_score * 0.55) + (avg_score * 0.45), 0.0, 1.0)

        adaptive_vector: list[dict[str, Any]] = []
        meta_weights = meta_payload.get("strategy_weights", [])
        if isinstance(meta_weights, list) and meta_weights:
            for row in meta_weights[:5]:
                if isinstance(row, Mapping):
                    adaptive_vector.append(
                        {
                            "strategy": str(row.get("strategy", "unknown")),
                            "total_weight": _safe_float(row.get("total_weight", 0.0), 0.0),
                            "adaptive_weight": _safe_float(row.get("adaptive_weight", 0.0), 0.0),
                            "exploration_weight": _safe_float(row.get("exploration_weight", 0.0), 0.0),
                            "exploitation_weight": _safe_float(row.get("exploitation_weight", 0.0), 0.0),
                        }
                    )
        if not adaptive_vector:
            for row in verdict.allocations[:5]:
                adaptive_vector.append(
                    {
                        "strategy": row.strategy,
                        "total_weight": float(row.weight),
                        "adaptive_weight": float(row.weight),
                        "exploration_weight": 0.0,
                        "exploitation_weight": 1.0,
                    }
                )

        explicit_meta_available = meta_payload.get("meta_available")
        if isinstance(explicit_meta_available, bool):
            meta_available = bool(explicit_meta_available)
        else:
            meta_available = bool(meta_payload) and (
                "regime_cluster" in meta_payload or "strategy_weights" in meta_payload or "risk_scale" in meta_payload
            )
        regime_confidence = _clamp(
            _safe_float(meta_payload.get("regime_confidence", world.market_state.regime_confidence), world.market_state.regime_confidence),
            0.0,
            1.0,
        )
        exploration_budget = _clamp(_safe_float(meta_payload.get("exploration_budget", 0.0), 0.0), 0.0, 1.0)
        exploitation_budget = _clamp(_safe_float(meta_payload.get("exploitation_budget", 1.0), 1.0), 0.0, 1.0)
        meta_risk_scale = _clamp(_safe_float(meta_payload.get("risk_scale", 1.0), 1.0), 0.0, 1.0)
        effective_confidence = _clamp(
            min(
                _safe_float(world.confidence_score, 0.0),
                _safe_float(world.risk_state.model_confidence, 0.0),
                _safe_float(mission.confidence, 0.0),
            ),
            0.0,
            1.0,
        )
        slippage_stress = _clamp(_safe_float(world.execution_state.slippage_bps, 0.0) / 20.0, 0.0, 1.0)
        infra_degradation = _clamp(
            max(
                _safe_float(world.infra_state.system_health_stress, 0.0),
                1.0 - _clamp(_safe_float(world.infra_state.health_score, 1.0), 0.0, 1.0),
            ),
            0.0,
            1.0,
        )
        account_stress = _clamp(
            max(
                _safe_float(world.portfolio_state.own_account_stress, 0.0),
                _safe_float(world.portfolio_state.exposure_ratio, 0.0),
                _safe_float(world.portfolio_state.concentration_score, 0.0),
            ),
            0.0,
            1.0,
        )
        stale_domains = set(world.stale_domains(max_age_s=45.0))
        critical_stale = [
            domain
            for domain in (
                "market_state",
                "execution_state",
                "infra_state",
                "risk_state",
            )
            if domain in stale_domains
        ]
        return cls(
            mission=str(mission.mission),
            mission_confidence=_clamp(_safe_float(mission.confidence, 0.0), 0.0, 1.0),
            mission_no_trade_preferred=bool(mission.no_trade_preferred),
            mission_allow_new_risk=bool(mission.allow_new_risk),
            parliament_no_trade=bool(verdict.no_trade),
            parliament_mode=str(verdict.selection_mode),
            parliament_top_score=_clamp(_safe_float(verdict.diagnostics.get("best_score", top_score), top_score), 0.0, 10.0),
            parliament_selected_count=max(0, int(len(verdict.selected_top))),
            strategy_health_score=strategy_health,
            weak_strategy_signals=max(0, int(weak)),
            strategy_health_vector=health_vector,
            adaptive_allocation_vector=adaptive_vector,
            regime_cluster=str(meta_payload.get("regime_cluster", world.market_state.regime) or world.market_state.regime or "unknown"),
            regime_confidence=regime_confidence,
            exploration_budget=exploration_budget,
            exploitation_budget=exploitation_budget,
            meta_risk_scale=meta_risk_scale,
            meta_available=meta_available,
            effective_confidence=effective_confidence,
            execution_stress=_clamp(_safe_float(world.execution_state.execution_stress, 0.0), 0.0, 1.0),
            slippage_stress=slippage_stress,
            infra_degradation=infra_degradation,
            stale_feed=bool(world.infra_state.stale_feed),
            desync=bool(world.infra_state.desync),
            world_state_available=bool(world.metadata.graph_available),
            critical_stale_domains=critical_stale,
            drawdown_pct=max(0.0, _safe_float(world.portfolio_state.drawdown_pct, 0.0)),
            account_stress=account_stress,
            risk_mode=str(world.risk_state.mode or "normal"),
            risk_hard_stop=bool(world.risk_state.hard_stop),
            risk_observe_only=bool(world.risk_state.observe_only),
            risk_flags=list(world.risk_state.risk_flags),
            plan_actionable=bool(plan.actionable),
            plan_side=str(plan.side or "flat").strip().lower(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission": self.mission,
            "mission_confidence": float(self.mission_confidence),
            "mission_no_trade_preferred": bool(self.mission_no_trade_preferred),
            "mission_allow_new_risk": bool(self.mission_allow_new_risk),
            "parliament_no_trade": bool(self.parliament_no_trade),
            "parliament_mode": self.parliament_mode,
            "parliament_top_score": float(self.parliament_top_score),
            "parliament_selected_count": int(self.parliament_selected_count),
            "strategy_health_score": float(self.strategy_health_score),
            "weak_strategy_signals": int(self.weak_strategy_signals),
            "strategy_health_vector": [dict(row) for row in self.strategy_health_vector],
            "adaptive_allocation_vector": [dict(row) for row in self.adaptive_allocation_vector],
            "regime_cluster": self.regime_cluster,
            "regime_confidence": float(self.regime_confidence),
            "exploration_budget": float(self.exploration_budget),
            "exploitation_budget": float(self.exploitation_budget),
            "meta_risk_scale": float(self.meta_risk_scale),
            "meta_available": bool(self.meta_available),
            "effective_confidence": float(self.effective_confidence),
            "execution_stress": float(self.execution_stress),
            "slippage_stress": float(self.slippage_stress),
            "infra_degradation": float(self.infra_degradation),
            "stale_feed": bool(self.stale_feed),
            "desync": bool(self.desync),
            "world_state_available": bool(self.world_state_available),
            "critical_stale_domains": list(self.critical_stale_domains),
            "drawdown_pct": float(self.drawdown_pct),
            "account_stress": float(self.account_stress),
            "risk_mode": self.risk_mode,
            "risk_hard_stop": bool(self.risk_hard_stop),
            "risk_observe_only": bool(self.risk_observe_only),
            "risk_flags": list(self.risk_flags),
            "plan_actionable": bool(self.plan_actionable),
            "plan_side": self.plan_side,
        }

    def strategy_health_summary(self) -> dict[str, Any]:
        return {
            "strategy_health_score": float(self.strategy_health_score),
            "weak_strategy_signals": int(self.weak_strategy_signals),
            "parliament_top_score": float(self.parliament_top_score),
            "parliament_selected_count": int(self.parliament_selected_count),
            "strategy_vector": [dict(row) for row in self.strategy_health_vector],
        }

    def meta_risk_summary(self) -> dict[str, Any]:
        return {
            "meta_available": bool(self.meta_available),
            "regime_cluster": self.regime_cluster,
            "regime_confidence": float(self.regime_confidence),
            "exploration_budget": float(self.exploration_budget),
            "exploitation_budget": float(self.exploitation_budget),
            "risk_scale": float(self.meta_risk_scale),
            "adaptive_allocation_vector": [dict(row) for row in self.adaptive_allocation_vector],
        }


@dataclass(frozen=True)
class ShieldEscalationDecision:
    previous_state: ShieldEscalationState
    new_state: ShieldEscalationState
    candidate_state: ShieldEscalationState
    escalation_severity: int
    reason_codes: tuple[str, ...]
    inputs_summary: dict[str, Any]
    strategy_health_summary: dict[str, Any]
    meta_risk_summary: dict[str, Any]
    hysteresis_state: ShieldHysteresisState
    no_trade_forced: bool
    hard_stop_forced: bool
    recovery_eligibility: dict[str, Any]
    override_record: ShieldOverrideRecord = field(default_factory=ShieldOverrideRecord)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
            "candidate_state": self.candidate_state.value,
            "escalation_severity": int(self.escalation_severity),
            "reason_codes": list(self.reason_codes),
            "inputs_summary": dict(self.inputs_summary),
            "strategy_health_summary": dict(self.strategy_health_summary),
            "meta_risk_summary": dict(self.meta_risk_summary),
            "hysteresis_state": self.hysteresis_state.to_dict(),
            "no_trade_forced": bool(self.no_trade_forced),
            "hard_stop_forced": bool(self.hard_stop_forced),
            "recovery_eligibility": dict(self.recovery_eligibility),
            "override_record": self.override_record.to_dict(),
        }


@dataclass(frozen=True)
class ShieldDecision:
    mode: str
    approved: bool
    size_scale: float
    reason_codes: list[str] = field(default_factory=list)
    kill_switch: bool = False
    previous_mode: str = ShieldEscalationState.NORMAL.value
    escalation_severity: int = 0
    escalation_reason_codes: list[str] = field(default_factory=list)
    escalation_inputs_summary: dict[str, Any] = field(default_factory=dict)
    strategy_health_summary: dict[str, Any] = field(default_factory=dict)
    meta_risk_summary: dict[str, Any] = field(default_factory=dict)
    hysteresis_state: dict[str, Any] = field(default_factory=dict)
    no_trade_forced: bool = False
    hard_stop_forced: bool = False
    recovery_eligibility: dict[str, Any] = field(default_factory=dict)
    override_record: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "shield_mode": self.mode,
            "previous_mode": self.previous_mode,
            "previous_shield_mode": self.previous_mode,
            "approved": self.approved,
            "size_scale": self.size_scale,
            "reason_codes": list(self.reason_codes),
            "escalation_severity": int(self.escalation_severity),
            "escalation_reason_codes": list(self.escalation_reason_codes or self.reason_codes),
            "escalation_inputs_summary": dict(self.escalation_inputs_summary),
            "strategy_health_summary": dict(self.strategy_health_summary),
            "meta_risk_summary": dict(self.meta_risk_summary),
            "hysteresis_state": dict(self.hysteresis_state),
            "no_trade_forced": bool(self.no_trade_forced),
            "hard_stop_forced": bool(self.hard_stop_forced),
            "recovery_eligibility": dict(self.recovery_eligibility),
            "override_record": dict(self.override_record),
            "kill_switch": self.kill_switch,
        }


class UniverseShield:
    """Unified safety layer across model, execution, venue, and telemetry stress."""

    def __init__(self, *, deescalation_windows: Mapping[str, int] | None = None) -> None:
        self._hysteresis = ShieldHysteresisState()
        defaults = {
            ShieldEscalationState.NORMAL.value: 0,
            ShieldEscalationState.CAUTIOUS.value: 2,
            ShieldEscalationState.DEFENSIVE.value: 3,
            ShieldEscalationState.OBSERVE_ONLY.value: 4,
            ShieldEscalationState.HARD_STOP.value: 5,
        }
        for key, value in dict(deescalation_windows or {}).items():
            defaults[str(key)] = max(0, int(value))
        self._deescalation_windows = defaults

    def hysteresis_snapshot(self) -> dict[str, Any]:
        return self._hysteresis.to_dict()

    def assess(
        self,
        *,
        world: WorldStateSnapshot,
        mission: MissionDecision,
        verdict: ParliamentVerdict,
        plan: ExecutionPlan,
        meta_diagnostics: Mapping[str, Any] | Any | None = None,
        cycle_id: str = "",
    ) -> ShieldDecision:
        envelope = ShieldHealthEnvelope.from_inputs(
            world=world,
            mission=mission,
            verdict=verdict,
            plan=plan,
            meta_diagnostics=meta_diagnostics,
        )
        candidate_state, reasons, override = self._candidate_state(envelope)
        escalation = self._with_hysteresis(
            candidate_state=candidate_state,
            reason_codes=reasons,
            envelope=envelope,
            cycle_id=cycle_id,
            override=override,
        )
        approved, size_scale = self._approval_for(
            escalation.new_state,
            plan=plan,
            mission=mission,
        )
        reason_codes = list(escalation.reason_codes)
        kill_switch = bool(escalation.hard_stop_forced or escalation.new_state == ShieldEscalationState.HARD_STOP)
        return ShieldDecision(
            mode=escalation.new_state.value,
            approved=approved,
            size_scale=size_scale,
            reason_codes=reason_codes,
            kill_switch=kill_switch,
            previous_mode=escalation.previous_state.value,
            escalation_severity=int(escalation.escalation_severity),
            escalation_reason_codes=reason_codes,
            escalation_inputs_summary=dict(escalation.inputs_summary),
            strategy_health_summary=dict(escalation.strategy_health_summary),
            meta_risk_summary=dict(escalation.meta_risk_summary),
            hysteresis_state=escalation.hysteresis_state.to_dict(),
            no_trade_forced=bool(escalation.no_trade_forced),
            hard_stop_forced=bool(escalation.hard_stop_forced),
            recovery_eligibility=dict(escalation.recovery_eligibility),
            override_record=escalation.override_record.to_dict(),
        )

    def _candidate_state(self, envelope: ShieldHealthEnvelope) -> tuple[ShieldEscalationState, list[str], ShieldOverrideRecord]:
        override = ShieldOverrideRecord()
        reasons: list[str] = []

        if envelope.risk_hard_stop or envelope.risk_mode == ShieldEscalationState.HARD_STOP.value:
            override = ShieldOverrideRecord(
                applied=True,
                override_type="legacy_hard_safety",
                reason=ShieldEscalationReason.HARD_SAFETY_DOCTRINE.value,
                no_trade_forced=True,
                hard_stop_forced=True,
            )
            return (
                ShieldEscalationState.HARD_STOP,
                [
                    ShieldEscalationReason.HARD_SAFETY_DOCTRINE.value,
                    ShieldEscalationReason.CRITICAL_MULTI_FACTOR_FAILURE.value,
                ],
                override,
            )

        if envelope.risk_observe_only:
            override = ShieldOverrideRecord(
                applied=True,
                override_type="legacy_observe_only",
                reason=ShieldEscalationReason.HARD_SAFETY_DOCTRINE.value,
                no_trade_forced=True,
                hard_stop_forced=False,
            )
            return (
                ShieldEscalationState.OBSERVE_ONLY,
                [ShieldEscalationReason.HARD_SAFETY_DOCTRINE.value],
                override,
            )

        hard_stack = 0
        if envelope.execution_stress >= 0.90 or envelope.slippage_stress >= 0.90:
            hard_stack += 1
            reasons.append(ShieldEscalationReason.EXECUTION_INFRA_FAILURE_STACK.value)
        if envelope.infra_degradation >= 0.85 or (envelope.stale_feed and envelope.desync):
            hard_stack += 1
            reasons.append(ShieldEscalationReason.EXECUTION_INFRA_FAILURE_STACK.value)
        if envelope.drawdown_pct >= 0.15 or envelope.account_stress >= 0.90:
            hard_stack += 1
            reasons.append(ShieldEscalationReason.CRITICAL_MULTI_FACTOR_FAILURE.value)
        if envelope.effective_confidence <= 0.10:
            hard_stack += 1
            reasons.append(ShieldEscalationReason.CONFIDENCE_COLLAPSE.value)
        if hard_stack >= 3:
            return ShieldEscalationState.HARD_STOP, _dedupe_codes(reasons), override

        observe_reasons: list[str] = []
        if (
            not envelope.world_state_available
            or envelope.stale_feed
            or envelope.desync
            or bool(envelope.critical_stale_domains)
        ):
            observe_reasons.append(ShieldEscalationReason.STALE_OR_DEGRADED_DATA.value)
        if envelope.effective_confidence <= 0.30 or envelope.regime_confidence <= 0.20:
            observe_reasons.append(ShieldEscalationReason.CONFIDENCE_COLLAPSE.value)
        if envelope.meta_available and envelope.exploration_budget >= 0.65:
            observe_reasons.append(ShieldEscalationReason.EXPLORATION_BUDGET_UNSAFE.value)
        if (
            envelope.mission_no_trade_preferred
            and envelope.parliament_no_trade
            and (envelope.meta_risk_scale <= 0.55 or envelope.strategy_health_score <= 0.45)
        ):
            observe_reasons.append(ShieldEscalationReason.NO_TRADE_CONVERGENCE.value)
        if observe_reasons:
            return ShieldEscalationState.OBSERVE_ONLY, _dedupe_codes(observe_reasons), override

        defensive_reasons: list[str] = []
        if envelope.execution_stress >= 0.65 and (
            envelope.infra_degradation >= 0.55
            or envelope.account_stress >= 0.60
            or envelope.drawdown_pct >= 0.08
        ):
            defensive_reasons.append(ShieldEscalationReason.EXECUTION_INFRA_ACCOUNT_COMPOUND_STRESS.value)
        if envelope.weak_strategy_signals >= 2 and envelope.strategy_health_score <= 0.55:
            defensive_reasons.append(ShieldEscalationReason.MULTI_STRATEGY_DECAY.value)
        if envelope.drawdown_pct >= 0.08 or envelope.account_stress >= 0.70:
            defensive_reasons.append(ShieldEscalationReason.PORTFOLIO_STRESS_DEFENSIVE.value)
        if defensive_reasons:
            return ShieldEscalationState.DEFENSIVE, _dedupe_codes(defensive_reasons), override

        cautious_reasons: list[str] = []
        if envelope.meta_available:
            if envelope.meta_risk_scale < 0.80 or envelope.exploration_budget >= 0.45:
                cautious_reasons.append(ShieldEscalationReason.META_DIAGNOSTICS_DEGRADED.value)
        else:
            cautious_reasons.append(ShieldEscalationReason.META_DIAGNOSTICS_UNAVAILABLE.value)
        if envelope.strategy_health_score < 0.65 or envelope.weak_strategy_signals >= 1:
            cautious_reasons.append(ShieldEscalationReason.STRATEGY_HEALTH_WEAKENING.value)
        if envelope.execution_stress >= 0.45 or envelope.slippage_stress >= 0.45:
            cautious_reasons.append(ShieldEscalationReason.EXECUTION_STRESS_RISING.value)
        if 0.20 < envelope.regime_confidence < 0.55:
            cautious_reasons.append(ShieldEscalationReason.REGIME_CONFIDENCE_WEAKENING.value)
        if cautious_reasons:
            return ShieldEscalationState.CAUTIOUS, _dedupe_codes(cautious_reasons), override

        return ShieldEscalationState.NORMAL, [ShieldEscalationReason.NORMAL_BASELINE.value], override

    def _with_hysteresis(
        self,
        *,
        candidate_state: ShieldEscalationState,
        reason_codes: list[str],
        envelope: ShieldHealthEnvelope,
        cycle_id: str,
        override: ShieldOverrideRecord,
    ) -> ShieldEscalationDecision:
        previous = self._hysteresis.active_state
        previous_idx = _STATE_ORDER[previous]
        candidate_idx = _STATE_ORDER[candidate_state]
        recovery_ready = self._recovery_ready(envelope)
        recovery_streak = int(self._hysteresis.recovery_streak)
        hold_count = int(self._hysteresis.hold_count)
        transitions = int(self._hysteresis.transitions)
        final_state = candidate_state
        hysteresis_reasons: list[str] = []

        if candidate_idx > previous_idx:
            recovery_streak = 0
            hold_count = 0
            if candidate_state != previous:
                transitions += 1
        elif candidate_idx < previous_idx:
            required = max(0, int(self._deescalation_windows.get(previous.value, 2)))
            if recovery_ready:
                recovery_streak += 1
            else:
                recovery_streak = 0
            if recovery_streak >= required and required > 0:
                stepped_idx = max(candidate_idx, previous_idx - 1)
                final_state = _STATE_SEQUENCE[stepped_idx]
                if stepped_idx < previous_idx:
                    transitions += 1
                    hysteresis_reasons.append(ShieldEscalationReason.SUSTAINED_RECOVERY.value)
                recovery_streak = 0
                hold_count = 0
            else:
                final_state = previous
                hold_count += 1
                hysteresis_reasons.append(ShieldEscalationReason.HYSTERESIS_HOLD.value)
        else:
            if recovery_ready and previous_idx > 0:
                recovery_streak = min(recovery_streak + 1, 10_000)
            else:
                recovery_streak = 0

        merged_reasons = _dedupe_codes(list(reason_codes) + hysteresis_reasons)
        next_hysteresis = ShieldHysteresisState(
            active_state=final_state,
            candidate_state=candidate_state,
            recovery_streak=max(0, recovery_streak),
            hold_count=max(0, hold_count),
            transitions=max(0, transitions),
            decisions=max(0, int(self._hysteresis.decisions) + 1),
            last_reason_codes=tuple(merged_reasons[:16]),
            last_cycle_id=str(cycle_id or self._hysteresis.last_cycle_id),
        )
        self._hysteresis = next_hysteresis

        required = max(0, int(self._deescalation_windows.get(previous.value, 2)))
        recovery_summary = {
            "ready": bool(recovery_ready),
            "required_streak": int(required),
            "accumulated_streak": int(next_hysteresis.recovery_streak),
            "candidate_state": candidate_state.value,
            "deescalation_ready": bool(candidate_idx < previous_idx and recovery_ready and next_hysteresis.recovery_streak >= required),
            "held_by_hysteresis": bool(final_state == previous and candidate_idx < previous_idx),
        }
        no_trade_forced = final_state in {ShieldEscalationState.OBSERVE_ONLY, ShieldEscalationState.HARD_STOP}
        hard_stop_forced = final_state == ShieldEscalationState.HARD_STOP
        return ShieldEscalationDecision(
            previous_state=previous,
            new_state=final_state,
            candidate_state=candidate_state,
            escalation_severity=max(0, _STATE_ORDER[final_state] - _STATE_ORDER[previous]),
            reason_codes=tuple(merged_reasons),
            inputs_summary=envelope.to_dict(),
            strategy_health_summary=envelope.strategy_health_summary(),
            meta_risk_summary=envelope.meta_risk_summary(),
            hysteresis_state=next_hysteresis,
            no_trade_forced=no_trade_forced,
            hard_stop_forced=hard_stop_forced,
            recovery_eligibility=recovery_summary,
            override_record=override,
        )

    def _recovery_ready(self, envelope: ShieldHealthEnvelope) -> bool:
        return bool(
            envelope.world_state_available
            and not envelope.stale_feed
            and not envelope.desync
            and not envelope.critical_stale_domains
            and envelope.execution_stress < 0.35
            and envelope.slippage_stress < 0.40
            and envelope.infra_degradation < 0.35
            and envelope.drawdown_pct < 0.06
            and envelope.account_stress < 0.55
            and envelope.effective_confidence > 0.55
            and envelope.regime_confidence > 0.50
            and envelope.strategy_health_score >= 0.65
            and (not envelope.meta_available or envelope.meta_risk_scale >= 0.80)
        )

    def _approval_for(self, state: ShieldEscalationState, *, plan: ExecutionPlan, mission: MissionDecision) -> tuple[bool, float]:
        if state == ShieldEscalationState.HARD_STOP:
            return False, 0.0
        if state == ShieldEscalationState.OBSERVE_ONLY:
            return False, 0.0
        if state == ShieldEscalationState.DEFENSIVE:
            if str(plan.side or "flat").lower() == "buy" and not mission.allow_new_risk:
                return False, 0.0
            if str(plan.side or "flat").lower() == "buy":
                return False, 0.0
            return True, 0.35
        if state == ShieldEscalationState.CAUTIOUS:
            return True, 0.50
        return True, 1.0
