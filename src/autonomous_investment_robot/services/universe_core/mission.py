from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .state import WorldStateSnapshot


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


class MissionType(str, Enum):
    PRESERVE_CAPITAL = "preserve_capital"
    OBSERVATION_ONLY = "observation_only"
    LOW_RISK_ACCUMULATION = "low_risk_accumulation"
    MOMENTUM_EXTRACTION = "momentum_extraction"
    MEAN_REVERSION_HARVEST = "mean_reversion_harvest"
    SPREAD_CAPTURE = "spread_capture"
    INVENTORY_UNWIND = "inventory_unwind"
    RISK_OFF_DEFENSE = "risk_off_defense"
    CARRY_EXTRACTION = "carry_extraction"


class MissionReasonCode(str, Enum):
    HARD_STOP_ACTIVE = "hard_stop_active"
    OBSERVE_ONLY_GUARD = "observe_only_guard"
    WORLD_STATE_UNAVAILABLE = "world_state_unavailable"
    INFRA_OR_DATA_STRESS = "infra_or_data_stress"
    EXECUTION_DEGRADATION = "execution_degradation"
    DRAWDOWN_PRESSURE = "drawdown_pressure"
    RISK_OFF_POSTURE = "risk_off_posture"
    ACCOUNT_STRESS = "account_stress"
    CONFIDENCE_SOFT = "confidence_soft"
    INVENTORY_PRESSURE = "inventory_pressure"
    TREND_CONFIRMED = "trend_confirmed"
    HEALTHY_LIQUIDITY = "healthy_liquidity"
    RANGE_DETECTED = "range_detected"
    CHEAP_EXECUTION = "cheap_execution"
    PASSIVE_EDGE_WINDOW = "passive_edge_window"
    MODERATE_CONVICTION = "moderate_conviction"
    DEFAULT_OBSERVATION = "default_observation"
    MISSION_ENGINE_FAILURE = "mission_engine_failure"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    TRANSITION = "transition"


class StrategyFamily(str, Enum):
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    SPREAD_CAPTURE = "spread_capture"
    CARRY = "carry"
    DEFENSIVE = "defensive"
    GUARDIAN = "guardian"
    UNKNOWN = "unknown"


MISSION_TAXONOMY: tuple[str, ...] = tuple(member.value for member in MissionType)


@dataclass(frozen=True)
class MissionPolicy:
    mission_type: MissionType
    allowed_strategy_families: tuple[str, ...]
    blocked_strategy_families: tuple[str, ...]
    execution_posture_hint: str
    shield_posture_hint: str
    aggressiveness_tier: str
    no_trade_preferred: bool
    clip_size_conservatively: bool
    default_size_scale: float
    default_urgency_bias: str
    allow_new_risk: bool
    duration_hint_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_type": self.mission_type.value,
            "allowed_strategy_families": list(self.allowed_strategy_families),
            "blocked_strategy_families": list(self.blocked_strategy_families),
            "execution_posture_hint": self.execution_posture_hint,
            "shield_posture_hint": self.shield_posture_hint,
            "aggressiveness_tier": self.aggressiveness_tier,
            "no_trade_preferred": self.no_trade_preferred,
            "clip_size_conservatively": self.clip_size_conservatively,
            "default_size_scale": self.default_size_scale,
            "default_urgency_bias": self.default_urgency_bias,
            "allow_new_risk": self.allow_new_risk,
            "duration_hint_s": self.duration_hint_s,
        }


@dataclass(frozen=True)
class MissionTransitionSummary:
    previous_mission: str
    current_mission: str
    changed: bool
    transition_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_mission": self.previous_mission,
            "current_mission": self.current_mission,
            "changed": self.changed,
            "transition_reason": self.transition_reason,
        }


@dataclass(frozen=True)
class MissionContext:
    world_state_available: bool
    world_freshness_s: dict[str, float]
    stale_or_desync: bool
    risk_mode: str
    hard_stop: bool
    observe_only: bool
    drawdown_pct: float
    own_account_stress: float
    exposure_ratio: float
    inventory_pressure: float
    execution_stress: float
    fill_ratio: float
    rejection_ratio: float
    confidence_score: float
    state_stability: float
    regime: str
    regime_confidence: float
    liquidity_regime: str
    volatility_regime: str
    expansion_state: str
    spread_bps: float
    trend_bias_bps: float
    tradable_primary_asset: bool
    primary_block_reasons: tuple[str, ...]
    disagreement_flag: bool
    severe_execution_degradation: bool
    degraded: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_state_available": self.world_state_available,
            "world_freshness_s": dict(self.world_freshness_s),
            "stale_or_desync": self.stale_or_desync,
            "risk_mode": self.risk_mode,
            "hard_stop": self.hard_stop,
            "observe_only": self.observe_only,
            "drawdown_pct": self.drawdown_pct,
            "own_account_stress": self.own_account_stress,
            "exposure_ratio": self.exposure_ratio,
            "inventory_pressure": self.inventory_pressure,
            "execution_stress": self.execution_stress,
            "fill_ratio": self.fill_ratio,
            "rejection_ratio": self.rejection_ratio,
            "confidence_score": self.confidence_score,
            "state_stability": self.state_stability,
            "regime": self.regime,
            "regime_confidence": self.regime_confidence,
            "liquidity_regime": self.liquidity_regime,
            "volatility_regime": self.volatility_regime,
            "expansion_state": self.expansion_state,
            "spread_bps": self.spread_bps,
            "trend_bias_bps": self.trend_bias_bps,
            "tradable_primary_asset": self.tradable_primary_asset,
            "primary_block_reasons": list(self.primary_block_reasons),
            "disagreement_flag": self.disagreement_flag,
            "severe_execution_degradation": self.severe_execution_degradation,
            "degraded": self.degraded,
        }


@dataclass(frozen=True)
class MissionDecision:
    mission_type: MissionType
    confidence: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    duration_hint_s: float = 60.0
    allowed_strategy_families: tuple[str, ...] = field(default_factory=tuple)
    blocked_strategy_families: tuple[str, ...] = field(default_factory=tuple)
    execution_posture_hint: str = "normal"
    shield_posture_hint: str = "normal"
    aggressiveness_tier: str = "balanced"
    no_trade_preferred: bool = False
    clip_size_conservatively: bool = False
    is_conservative_fallback: bool = False
    previous_mission: str = ""
    transition_reason: str = ""
    supporting_summary: dict[str, Any] = field(default_factory=dict)
    size_scale: float = 1.0
    urgency_bias: str = "normal"
    allow_new_risk: bool = True

    @property
    def mission(self) -> str:
        # Backward-compatible alias used by existing UNIVERSE CORE modules.
        return self.mission_type.value

    @property
    def rationale(self) -> list[str]:
        # Backward-compatible alias used by existing state projections.
        return list(self.reason_codes)

    def to_dict(self) -> dict[str, Any]:
        transition = MissionTransitionSummary(
            previous_mission=self.previous_mission,
            current_mission=self.mission,
            changed=bool(self.previous_mission and self.previous_mission != self.mission),
            transition_reason=self.transition_reason,
        )
        return {
            "mission": self.mission,
            "mission_type": self.mission,
            "confidence": float(self.confidence),
            "reason_codes": list(self.reason_codes),
            "rationale": list(self.reason_codes),
            "duration_hint_s": float(self.duration_hint_s),
            "expected_duration": float(self.duration_hint_s),
            "allowed_strategy_families": list(self.allowed_strategy_families),
            "blocked_strategy_families": list(self.blocked_strategy_families),
            "execution_posture_hint": self.execution_posture_hint,
            "shield_posture_hint": self.shield_posture_hint,
            "aggressiveness_tier": self.aggressiveness_tier,
            "aggressiveness_hint": self.aggressiveness_tier,
            "no_trade_preferred": bool(self.no_trade_preferred),
            "no_trade_preference": bool(self.no_trade_preferred),
            "clip_size_conservatively": bool(self.clip_size_conservatively),
            "is_conservative_fallback": bool(self.is_conservative_fallback),
            "fallback_flag": bool(self.is_conservative_fallback),
            "previous_mission": self.previous_mission,
            "transition_reason": self.transition_reason,
            "transition_summary": transition.to_dict(),
            "supporting_summary": dict(self.supporting_summary),
            "size_scale": float(self.size_scale),
            "urgency_bias": self.urgency_bias,
            "allow_new_risk": bool(self.allow_new_risk),
        }


def infer_strategy_family(strategy_name: str) -> str:
    value = str(strategy_name or "").strip().lower()
    if not value:
        return StrategyFamily.UNKNOWN.value
    if "guardian" in value or "no_trade" in value:
        return StrategyFamily.GUARDIAN.value
    if "momentum" in value or "breakout" in value or "trend" in value:
        return StrategyFamily.MOMENTUM.value
    if "mean_reversion" in value or "reversion" in value or "sweep" in value:
        return StrategyFamily.MEAN_REVERSION.value
    if "spread" in value or "maker" in value:
        return StrategyFamily.SPREAD_CAPTURE.value
    if "carry" in value or "funding" in value:
        return StrategyFamily.CARRY.value
    if "defensive" in value or "de_risk" in value:
        return StrategyFamily.DEFENSIVE.value
    return StrategyFamily.UNKNOWN.value


class MissionEngine:
    """Selects runtime objective from world, risk, execution, and health posture."""

    def __init__(self, policy_map: dict[MissionType, MissionPolicy] | None = None) -> None:
        self.policy_map = policy_map or self._default_policy_map()

    def build_context(self, world: WorldStateSnapshot) -> MissionContext:
        primary = world.market_state.primary_symbol or world.asset_state.primary_symbol
        primary_asset = world.asset_state.assets.get(primary, None) if primary else None
        freshness = world.freshness_by_domain() if hasattr(world, "freshness_by_domain") else {}
        disagreement = bool(world.strategy_state.disagreement_summary)
        severe_exec = world.execution_state.execution_stress >= 0.80 or world.execution_state.rejection_ratio >= 0.45
        degraded = bool(
            world.infra_state.stale_feed
            or world.infra_state.desync
            or world.infra_state.system_health_stress >= 0.70
            or max(freshness.values(), default=0.0) > 30.0
            or severe_exec
        )
        return MissionContext(
            world_state_available=bool(world.metadata.graph_available),
            world_freshness_s=dict(freshness),
            stale_or_desync=bool(world.infra_state.stale_feed or world.infra_state.desync),
            risk_mode=str(world.risk_state.mode or "normal"),
            hard_stop=bool(world.risk_state.hard_stop),
            observe_only=bool(world.risk_state.observe_only),
            drawdown_pct=max(0.0, float(world.portfolio_state.drawdown_pct)),
            own_account_stress=max(0.0, float(world.portfolio_state.own_account_stress)),
            exposure_ratio=max(0.0, float(world.portfolio_state.exposure_ratio)),
            inventory_pressure=max(0.0, float(world.portfolio_state.inventory_pressure)),
            execution_stress=max(0.0, float(world.execution_state.execution_stress)),
            fill_ratio=max(0.0, float(world.execution_state.fill_ratio)),
            rejection_ratio=max(0.0, float(world.execution_state.rejection_ratio)),
            confidence_score=max(0.0, min(float(world.confidence_score), float(world.risk_state.model_confidence))),
            state_stability=max(0.0, float(world.state_stability)),
            regime=str(world.market_state.regime or "RANGE"),
            regime_confidence=max(0.0, float(world.market_state.regime_confidence)),
            liquidity_regime=str(world.market_state.liquidity_regime or "NORMAL"),
            volatility_regime=str(world.market_state.volatility_regime or "LOW_VOL"),
            expansion_state=str(world.market_state.expansion_state or "COMPRESSION"),
            spread_bps=max(0.0, float(world.market_state.spread_bps)),
            trend_bias_bps=float(world.market_state.trend_bias_bps),
            tradable_primary_asset=bool(primary_asset is None or primary_asset.tradable),
            primary_block_reasons=tuple(primary_asset.block_reasons if primary_asset is not None else []),
            disagreement_flag=disagreement,
            severe_execution_degradation=severe_exec,
            degraded=degraded,
        )

    def choose(self, world: WorldStateSnapshot, *, previous_mission: str | MissionDecision | None = None) -> MissionDecision:
        previous = previous_mission.mission if isinstance(previous_mission, MissionDecision) else str(previous_mission or "")
        try:
            context = self.build_context(world)
            mission_type, reason_codes = self._select_mission(context)
            policy = self.policy_map.get(mission_type, self.policy_map[MissionType.OBSERVATION_ONLY])
            decision = self._build_decision(
                mission_type=mission_type,
                reason_codes=reason_codes,
                policy=policy,
                context=context,
                previous_mission=previous,
                fallback=False,
            )
            return decision
        except Exception:
            fallback_policy = self.policy_map[MissionType.OBSERVATION_ONLY]
            fallback_context = MissionContext(
                world_state_available=False,
                world_freshness_s={},
                stale_or_desync=True,
                risk_mode="unknown",
                hard_stop=False,
                observe_only=True,
                drawdown_pct=0.0,
                own_account_stress=1.0,
                exposure_ratio=0.0,
                inventory_pressure=0.0,
                execution_stress=1.0,
                fill_ratio=0.0,
                rejection_ratio=1.0,
                confidence_score=0.0,
                state_stability=0.0,
                regime="UNKNOWN",
                regime_confidence=0.0,
                liquidity_regime="UNKNOWN",
                volatility_regime="UNKNOWN",
                expansion_state="UNKNOWN",
                spread_bps=0.0,
                trend_bias_bps=0.0,
                tradable_primary_asset=False,
                primary_block_reasons=(),
                disagreement_flag=False,
                severe_execution_degradation=True,
                degraded=True,
            )
            return self._build_decision(
                mission_type=MissionType.OBSERVATION_ONLY,
                reason_codes=(MissionReasonCode.MISSION_ENGINE_FAILURE.value,),
                policy=fallback_policy,
                context=fallback_context,
                previous_mission=previous,
                fallback=True,
            )

    def _select_mission(self, context: MissionContext) -> tuple[MissionType, tuple[str, ...]]:
        reasons: list[str] = []
        if not context.world_state_available:
            return MissionType.OBSERVATION_ONLY, (
                MissionReasonCode.WORLD_STATE_UNAVAILABLE.value,
                MissionReasonCode.INSUFFICIENT_CONTEXT.value,
            )
        if context.hard_stop:
            return MissionType.OBSERVATION_ONLY, (MissionReasonCode.HARD_STOP_ACTIVE.value,)
        if context.observe_only:
            return MissionType.OBSERVATION_ONLY, (
                MissionReasonCode.OBSERVE_ONLY_GUARD.value,
                MissionReasonCode.RISK_OFF_POSTURE.value,
            )
        if context.stale_or_desync or context.degraded:
            return MissionType.OBSERVATION_ONLY, (
                MissionReasonCode.INFRA_OR_DATA_STRESS.value,
                MissionReasonCode.EXECUTION_DEGRADATION.value if context.severe_execution_degradation else MissionReasonCode.INSUFFICIENT_CONTEXT.value,
            )
        if context.drawdown_pct >= 0.08:
            return MissionType.PRESERVE_CAPITAL, (
                MissionReasonCode.DRAWDOWN_PRESSURE.value,
                MissionReasonCode.RISK_OFF_POSTURE.value,
            )
        if context.risk_mode in {"defensive", "observe-only"}:
            return MissionType.RISK_OFF_DEFENSE, (
                MissionReasonCode.DRAWDOWN_PRESSURE.value,
                MissionReasonCode.RISK_OFF_POSTURE.value,
            )
        if context.confidence_score <= 0.40:
            return MissionType.OBSERVATION_ONLY, (
                MissionReasonCode.CONFIDENCE_SOFT.value,
                MissionReasonCode.INSUFFICIENT_CONTEXT.value,
            )
        if context.own_account_stress >= 0.65:
            return MissionType.PRESERVE_CAPITAL, (
                MissionReasonCode.ACCOUNT_STRESS.value,
                MissionReasonCode.CONFIDENCE_SOFT.value,
            )
        if context.inventory_pressure >= 0.65 or (context.exposure_ratio >= 0.70 and context.regime != "TREND"):
            return MissionType.INVENTORY_UNWIND, (MissionReasonCode.INVENTORY_PRESSURE.value,)
        if (
            context.regime == "TREND"
            and context.liquidity_regime in {"NORMAL", "DEEP"}
            and context.execution_stress <= 0.45
            and context.state_stability >= 0.55
            and context.regime_confidence >= 0.55
        ):
            return MissionType.MOMENTUM_EXTRACTION, (
                MissionReasonCode.TREND_CONFIRMED.value,
                MissionReasonCode.HEALTHY_LIQUIDITY.value,
            )
        if (
            context.regime in {"RANGE", "UNKNOWN"}
            and context.expansion_state == "COMPRESSION"
            and context.execution_stress <= 0.40
            and context.state_stability >= 0.50
        ):
            return MissionType.MEAN_REVERSION_HARVEST, (
                MissionReasonCode.RANGE_DETECTED.value,
                MissionReasonCode.CHEAP_EXECUTION.value,
            )
        if (
            context.spread_bps >= 8.0
            and context.liquidity_regime in {"NORMAL", "DEEP"}
            and context.execution_stress <= 0.30
            and context.regime != "PANIC"
        ):
            return MissionType.SPREAD_CAPTURE, (MissionReasonCode.PASSIVE_EDGE_WINDOW.value,)
        if context.confidence_score >= 0.45 and context.state_stability >= 0.45 and context.regime != "PANIC":
            reasons.extend([MissionReasonCode.MODERATE_CONVICTION.value])
            return MissionType.LOW_RISK_ACCUMULATION, tuple(reasons)
        return MissionType.OBSERVATION_ONLY, (MissionReasonCode.DEFAULT_OBSERVATION.value,)

    def _build_decision(
        self,
        *,
        mission_type: MissionType,
        reason_codes: tuple[str, ...],
        policy: MissionPolicy,
        context: MissionContext,
        previous_mission: str,
        fallback: bool,
    ) -> MissionDecision:
        confidence = self._confidence(context, mission_type, fallback=fallback)
        transition_reason = ""
        if previous_mission and previous_mission != mission_type.value:
            transition_reason = f"{MissionReasonCode.TRANSITION.value}:{previous_mission}->{mission_type.value}"
        supporting_summary = {
            "context": context.to_dict(),
            "policy": policy.to_dict(),
        }
        size_scale = policy.default_size_scale
        if policy.clip_size_conservatively:
            size_scale = min(size_scale, 0.60)
        if context.execution_stress >= 0.50:
            size_scale *= 0.80
        if context.liquidity_regime == "THIN":
            size_scale *= 0.85
        if context.volatility_regime == "HIGH_VOL":
            size_scale *= 0.90
        return MissionDecision(
            mission_type=mission_type,
            confidence=confidence,
            reason_codes=tuple(reason_codes),
            duration_hint_s=policy.duration_hint_s,
            allowed_strategy_families=policy.allowed_strategy_families,
            blocked_strategy_families=policy.blocked_strategy_families,
            execution_posture_hint=policy.execution_posture_hint,
            shield_posture_hint=policy.shield_posture_hint,
            aggressiveness_tier=policy.aggressiveness_tier,
            no_trade_preferred=policy.no_trade_preferred,
            clip_size_conservatively=policy.clip_size_conservatively,
            is_conservative_fallback=fallback,
            previous_mission=previous_mission,
            transition_reason=transition_reason,
            supporting_summary=supporting_summary,
            size_scale=_clamp(size_scale, 0.0, 1.25),
            urgency_bias=policy.default_urgency_bias,
            allow_new_risk=policy.allow_new_risk and mission_type not in {MissionType.OBSERVATION_ONLY, MissionType.PRESERVE_CAPITAL, MissionType.RISK_OFF_DEFENSE},
        )

    def _confidence(self, context: MissionContext, mission_type: MissionType, *, fallback: bool) -> float:
        base = min(context.confidence_score, context.state_stability)
        if mission_type == MissionType.OBSERVATION_ONLY:
            base = max(base, 0.70 if context.degraded else 0.55)
        if mission_type in {MissionType.PRESERVE_CAPITAL, MissionType.RISK_OFF_DEFENSE, MissionType.INVENTORY_UNWIND}:
            base = max(base, 0.60)
        if fallback:
            base = 0.80
        return _clamp(base, 0.0, 1.0)

    def _default_policy_map(self) -> dict[MissionType, MissionPolicy]:
        return {
            MissionType.OBSERVATION_ONLY: MissionPolicy(
                mission_type=MissionType.OBSERVATION_ONLY,
                allowed_strategy_families=(StrategyFamily.GUARDIAN.value,),
                blocked_strategy_families=(StrategyFamily.MOMENTUM.value, StrategyFamily.MEAN_REVERSION.value, StrategyFamily.SPREAD_CAPTURE.value, StrategyFamily.CARRY.value),
                execution_posture_hint="none",
                shield_posture_hint="observe-only",
                aggressiveness_tier="none",
                no_trade_preferred=True,
                clip_size_conservatively=True,
                default_size_scale=0.0,
                default_urgency_bias="none",
                allow_new_risk=False,
                duration_hint_s=60.0,
            ),
            MissionType.PRESERVE_CAPITAL: MissionPolicy(
                mission_type=MissionType.PRESERVE_CAPITAL,
                allowed_strategy_families=(StrategyFamily.GUARDIAN.value, StrategyFamily.DEFENSIVE.value, StrategyFamily.SPREAD_CAPTURE.value),
                blocked_strategy_families=(StrategyFamily.MOMENTUM.value, StrategyFamily.CARRY.value),
                execution_posture_hint="de_risk",
                shield_posture_hint="defensive",
                aggressiveness_tier="low",
                no_trade_preferred=True,
                clip_size_conservatively=True,
                default_size_scale=0.25,
                default_urgency_bias="low",
                allow_new_risk=False,
                duration_hint_s=300.0,
            ),
            MissionType.RISK_OFF_DEFENSE: MissionPolicy(
                mission_type=MissionType.RISK_OFF_DEFENSE,
                allowed_strategy_families=(StrategyFamily.GUARDIAN.value, StrategyFamily.DEFENSIVE.value),
                blocked_strategy_families=(StrategyFamily.MOMENTUM.value, StrategyFamily.MEAN_REVERSION.value, StrategyFamily.CARRY.value),
                execution_posture_hint="risk_off",
                shield_posture_hint="hard_defensive",
                aggressiveness_tier="very_low",
                no_trade_preferred=True,
                clip_size_conservatively=True,
                default_size_scale=0.10,
                default_urgency_bias="high",
                allow_new_risk=False,
                duration_hint_s=240.0,
            ),
            MissionType.INVENTORY_UNWIND: MissionPolicy(
                mission_type=MissionType.INVENTORY_UNWIND,
                allowed_strategy_families=(StrategyFamily.DEFENSIVE.value, StrategyFamily.SPREAD_CAPTURE.value, StrategyFamily.GUARDIAN.value),
                blocked_strategy_families=(StrategyFamily.MOMENTUM.value, StrategyFamily.CARRY.value),
                execution_posture_hint="inventory_unwind",
                shield_posture_hint="defensive",
                aggressiveness_tier="low",
                no_trade_preferred=False,
                clip_size_conservatively=True,
                default_size_scale=0.35,
                default_urgency_bias="normal",
                allow_new_risk=False,
                duration_hint_s=180.0,
            ),
            MissionType.MOMENTUM_EXTRACTION: MissionPolicy(
                mission_type=MissionType.MOMENTUM_EXTRACTION,
                allowed_strategy_families=(StrategyFamily.MOMENTUM.value, StrategyFamily.SPREAD_CAPTURE.value, StrategyFamily.GUARDIAN.value),
                blocked_strategy_families=(StrategyFamily.CARRY.value,),
                execution_posture_hint="aggressive_if_quality",
                shield_posture_hint="normal",
                aggressiveness_tier="high",
                no_trade_preferred=False,
                clip_size_conservatively=False,
                default_size_scale=1.00,
                default_urgency_bias="high",
                allow_new_risk=True,
                duration_hint_s=90.0,
            ),
            MissionType.MEAN_REVERSION_HARVEST: MissionPolicy(
                mission_type=MissionType.MEAN_REVERSION_HARVEST,
                allowed_strategy_families=(StrategyFamily.MEAN_REVERSION.value, StrategyFamily.SPREAD_CAPTURE.value, StrategyFamily.GUARDIAN.value),
                blocked_strategy_families=(StrategyFamily.CARRY.value,),
                execution_posture_hint="patient_limit",
                shield_posture_hint="normal",
                aggressiveness_tier="medium",
                no_trade_preferred=False,
                clip_size_conservatively=False,
                default_size_scale=0.70,
                default_urgency_bias="normal",
                allow_new_risk=True,
                duration_hint_s=180.0,
            ),
            MissionType.SPREAD_CAPTURE: MissionPolicy(
                mission_type=MissionType.SPREAD_CAPTURE,
                allowed_strategy_families=(StrategyFamily.SPREAD_CAPTURE.value, StrategyFamily.GUARDIAN.value),
                blocked_strategy_families=(StrategyFamily.MOMENTUM.value,),
                execution_posture_hint="maker_first",
                shield_posture_hint="normal",
                aggressiveness_tier="low_medium",
                no_trade_preferred=False,
                clip_size_conservatively=True,
                default_size_scale=0.45,
                default_urgency_bias="low",
                allow_new_risk=True,
                duration_hint_s=240.0,
            ),
            MissionType.LOW_RISK_ACCUMULATION: MissionPolicy(
                mission_type=MissionType.LOW_RISK_ACCUMULATION,
                allowed_strategy_families=(StrategyFamily.MOMENTUM.value, StrategyFamily.MEAN_REVERSION.value, StrategyFamily.SPREAD_CAPTURE.value, StrategyFamily.GUARDIAN.value),
                blocked_strategy_families=(),
                execution_posture_hint="balanced",
                shield_posture_hint="cautious",
                aggressiveness_tier="medium",
                no_trade_preferred=False,
                clip_size_conservatively=True,
                default_size_scale=0.75,
                default_urgency_bias="normal",
                allow_new_risk=True,
                duration_hint_s=180.0,
            ),
            MissionType.CARRY_EXTRACTION: MissionPolicy(
                mission_type=MissionType.CARRY_EXTRACTION,
                allowed_strategy_families=(StrategyFamily.CARRY.value, StrategyFamily.DEFENSIVE.value, StrategyFamily.GUARDIAN.value),
                blocked_strategy_families=(StrategyFamily.MOMENTUM.value,),
                execution_posture_hint="carry_window",
                shield_posture_hint="cautious",
                aggressiveness_tier="low",
                no_trade_preferred=False,
                clip_size_conservatively=True,
                default_size_scale=0.55,
                default_urgency_bias="low",
                allow_new_risk=True,
                duration_hint_s=600.0,
            ),
        }
