from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping

from .execution import ExecutionPlan
from .mission import MissionDecision
from .parliament import StrategyProposal
from .state import WorldStateSnapshot


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


class ExecutionPersonalityMode(str, Enum):
    STEALTH_PASSIVE = "STEALTH_PASSIVE"
    BALANCED_ALPHA = "BALANCED_ALPHA"
    AGGRESSIVE_CAPTURE = "AGGRESSIVE_CAPTURE"
    LIQUIDITY_SNIPER = "LIQUIDITY_SNIPER"
    PANIC_EXIT = "PANIC_EXIT"


@dataclass(frozen=True)
class OrderBookShapeModel:
    spread_bps: float
    depth_notional: float
    participation_ratio: float
    order_flow_imbalance: float
    thin_book: bool
    wide_spread: bool
    sudden_depth_drop: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "spread_bps": float(self.spread_bps),
            "depth_notional": float(self.depth_notional),
            "participation_ratio": float(self.participation_ratio),
            "order_flow_imbalance": float(self.order_flow_imbalance),
            "thin_book": bool(self.thin_book),
            "wide_spread": bool(self.wide_spread),
            "sudden_depth_drop": bool(self.sudden_depth_drop),
        }


@dataclass(frozen=True)
class SlippageImpactEstimator:
    expected_slippage_bps: float
    impact_risk: float
    fee_drag_bps: float
    spread_cross_cost_bps: float
    expected_total_cost_bps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_slippage_bps": float(self.expected_slippage_bps),
            "impact_risk": float(self.impact_risk),
            "fee_drag_bps": float(self.fee_drag_bps),
            "spread_cross_cost_bps": float(self.spread_cross_cost_bps),
            "expected_total_cost_bps": float(self.expected_total_cost_bps),
        }


@dataclass(frozen=True)
class ExecutionElasticityCurve:
    slope: float
    curvature: float
    elasticity_band: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "slope": float(self.slope),
            "curvature": float(self.curvature),
            "elasticity_band": self.elasticity_band,
        }


@dataclass(frozen=True)
class QueuePositionEstimator:
    queue_quality: float
    expected_queue_rank: float
    queue_decay_risk: float
    fill_probability_estimate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_quality": float(self.queue_quality),
            "expected_queue_rank": float(self.expected_queue_rank),
            "queue_decay_risk": float(self.queue_decay_risk),
            "fill_probability_estimate": float(self.fill_probability_estimate),
        }


@dataclass(frozen=True)
class ExecutionSlice:
    idx: int
    notional_quote: float
    wait_s: float
    max_slippage_bps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "idx": int(self.idx),
            "notional_quote": float(self.notional_quote),
            "wait_s": float(self.wait_s),
            "max_slippage_bps": float(self.max_slippage_bps),
        }


@dataclass(frozen=True)
class DynamicOrderSlicer:
    slicing_mode: str
    slice_count: int
    slice_interval_s: float
    participation_rate: float
    slices: list[ExecutionSlice] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slicing_mode": self.slicing_mode,
            "slice_count": int(self.slice_count),
            "slice_interval_s": float(self.slice_interval_s),
            "participation_rate": float(self.participation_rate),
            "slices": [row.to_dict() for row in self.slices],
        }


@dataclass(frozen=True)
class SpreadBreathingAnalyzer:
    stress_score: float
    breathing_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "stress_score": float(self.stress_score),
            "breathing_flag": bool(self.breathing_flag),
        }


@dataclass(frozen=True)
class MicroVolatilityBurstDetector:
    stress_score: float
    burst_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "stress_score": float(self.stress_score),
            "burst_flag": bool(self.burst_flag),
        }


@dataclass(frozen=True)
class LiquidityVacuumDetector:
    stress_score: float
    vacuum_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "stress_score": float(self.stress_score),
            "vacuum_flag": bool(self.vacuum_flag),
        }


@dataclass(frozen=True)
class OrderFlowToxicityHeuristic:
    toxicity_score: float
    toxic_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "toxicity_score": float(self.toxicity_score),
            "toxic_flag": bool(self.toxic_flag),
        }


@dataclass(frozen=True)
class SpoofLikeDepthOscillationHeuristic:
    oscillation_score: float
    spoof_like_flag: bool
    oscillation_direction: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "oscillation_score": float(self.oscillation_score),
            "spoof_like_flag": bool(self.spoof_like_flag),
            "oscillation_direction": self.oscillation_direction,
        }


@dataclass(frozen=True)
class ExecutionStressIndex:
    score: float
    spread_breathing: float
    micro_vol_burst: float
    liquidity_vacuum: float
    toxicity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": float(self.score),
            "spread_breathing": float(self.spread_breathing),
            "micro_vol_burst": float(self.micro_vol_burst),
            "liquidity_vacuum": float(self.liquidity_vacuum),
            "toxicity": float(self.toxicity),
        }


@dataclass(frozen=True)
class FillUncertaintyEnvelope:
    expected_fill_probability: float
    lower_bound: float
    upper_bound: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_fill_probability": float(self.expected_fill_probability),
            "lower_bound": float(self.lower_bound),
            "upper_bound": float(self.upper_bound),
        }


@dataclass(frozen=True)
class AdverseSelectionProbabilityModel:
    probability: float
    risk_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "probability": float(self.probability),
            "risk_flag": bool(self.risk_flag),
        }


@dataclass(frozen=True)
class CapitalAtFillRisk:
    capital_at_fill_risk_quote: float
    risk_ratio_to_edge: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "capital_at_fill_risk_quote": float(self.capital_at_fill_risk_quote),
            "risk_ratio_to_edge": float(self.risk_ratio_to_edge),
        }


@dataclass(frozen=True)
class ExchangeLatencyDriftMonitor:
    latency_ms: float
    drift_score: float
    degraded: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "latency_ms": float(self.latency_ms),
            "drift_score": float(self.drift_score),
            "degraded": bool(self.degraded),
        }


@dataclass(frozen=True)
class MatchingEngineAnomalySignal:
    anomaly_score: float
    anomaly_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_score": float(self.anomaly_score),
            "anomaly_flag": bool(self.anomaly_flag),
        }


@dataclass(frozen=True)
class WithdrawalLiquidityRiskFlag:
    risk_score: float
    risk_flag: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_score": float(self.risk_score),
            "risk_flag": bool(self.risk_flag),
        }


@dataclass(frozen=True)
class APIErrorRateHealthScore:
    health_score: float
    degraded: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_score": float(self.health_score),
            "degraded": bool(self.degraded),
        }


@dataclass(frozen=True)
class ExecutionQualityEstimate:
    expected_fill_quality: float
    expected_total_cost_bps: float
    expected_net_edge_bps: float
    execution_quality_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_fill_quality": float(self.expected_fill_quality),
            "expected_total_cost_bps": float(self.expected_total_cost_bps),
            "expected_net_edge_bps": float(self.expected_net_edge_bps),
            "execution_quality_score": float(self.execution_quality_score),
        }


@dataclass(frozen=True)
class ExecutionAbortDecision:
    should_abort: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_abort": bool(self.should_abort),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class PanicFlattenProtocol:
    max_loss_bps: float
    slice_weights: tuple[float, ...]
    ioc_timeout_s: float
    allow_cross_spread: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_loss_bps": float(self.max_loss_bps),
            "slice_weights": [float(weight) for weight in self.slice_weights],
            "ioc_timeout_s": float(self.ioc_timeout_s),
            "allow_cross_spread": bool(self.allow_cross_spread),
        }


@dataclass(frozen=True)
class FrozenOrderRecoveryRoutine:
    max_recovery_attempts: int
    cancel_backoff_s: float
    force_taker_after_attempts: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_recovery_attempts": int(self.max_recovery_attempts),
            "cancel_backoff_s": float(self.cancel_backoff_s),
            "force_taker_after_attempts": int(self.force_taker_after_attempts),
        }


@dataclass(frozen=True)
class LiquidityCrashExitStrategy:
    cliff_depth_threshold_quote: float
    max_participation_rate: float
    emergency_slippage_cap_bps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "cliff_depth_threshold_quote": float(self.cliff_depth_threshold_quote),
            "max_participation_rate": float(self.max_participation_rate),
            "emergency_slippage_cap_bps": float(self.emergency_slippage_cap_bps),
        }


@dataclass(frozen=True)
class GradualDeRiskLadder:
    steps: tuple[float, ...]
    step_interval_s: float
    stop_if_recovered: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [float(step) for step in self.steps],
            "step_interval_s": float(self.step_interval_s),
            "stop_if_recovered": bool(self.stop_if_recovered),
        }


@dataclass(frozen=True)
class CapitalSurvivalDoctrine:
    protocol: str
    panic_flatten: PanicFlattenProtocol | None = None
    frozen_order_recovery: FrozenOrderRecoveryRoutine | None = None
    liquidity_crash_exit: LiquidityCrashExitStrategy | None = None
    gradual_derisk: GradualDeRiskLadder | None = None
    bounded_execution_loss_quote: float = 0.0
    replay_safe_signature: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "panic_flatten": None if self.panic_flatten is None else self.panic_flatten.to_dict(),
            "frozen_order_recovery": None
            if self.frozen_order_recovery is None
            else self.frozen_order_recovery.to_dict(),
            "liquidity_crash_exit": None if self.liquidity_crash_exit is None else self.liquidity_crash_exit.to_dict(),
            "gradual_derisk": None if self.gradual_derisk is None else self.gradual_derisk.to_dict(),
            "bounded_execution_loss_quote": float(self.bounded_execution_loss_quote),
            "replay_safe_signature": self.replay_safe_signature,
        }


@dataclass(frozen=True)
class ExecutionDecisionEnvelope:
    mode: ExecutionPersonalityMode
    plan: ExecutionPlan
    order_book_shape: OrderBookShapeModel
    slippage_impact: SlippageImpactEstimator
    elasticity_curve: ExecutionElasticityCurve
    queue_estimate: QueuePositionEstimator
    slicer: DynamicOrderSlicer
    stress_index: ExecutionStressIndex
    spoofing_heuristic: SpoofLikeDepthOscillationHeuristic
    fill_uncertainty: FillUncertaintyEnvelope
    adverse_selection: AdverseSelectionProbabilityModel
    capital_at_fill_risk: CapitalAtFillRisk
    latency_drift: ExchangeLatencyDriftMonitor
    matching_engine_anomaly: MatchingEngineAnomalySignal
    withdrawal_liquidity_risk: WithdrawalLiquidityRiskFlag
    api_health: APIErrorRateHealthScore
    quality_estimate: ExecutionQualityEstimate
    abort_decision: ExecutionAbortDecision
    survival_doctrine: CapitalSurvivalDoctrine
    risk_scale_hint: float
    advisory_escalation: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "plan": self.plan.to_dict(),
            "order_book_shape": self.order_book_shape.to_dict(),
            "slippage_impact": self.slippage_impact.to_dict(),
            "elasticity_curve": self.elasticity_curve.to_dict(),
            "queue_estimate": self.queue_estimate.to_dict(),
            "slicer": self.slicer.to_dict(),
            "stress_index": self.stress_index.to_dict(),
            "spoofing_heuristic": self.spoofing_heuristic.to_dict(),
            "fill_uncertainty": self.fill_uncertainty.to_dict(),
            "adverse_selection": self.adverse_selection.to_dict(),
            "capital_at_fill_risk": self.capital_at_fill_risk.to_dict(),
            "latency_drift": self.latency_drift.to_dict(),
            "matching_engine_anomaly": self.matching_engine_anomaly.to_dict(),
            "withdrawal_liquidity_risk": self.withdrawal_liquidity_risk.to_dict(),
            "api_health": self.api_health.to_dict(),
            "quality_estimate": self.quality_estimate.to_dict(),
            "abort_decision": self.abort_decision.to_dict(),
            "survival_doctrine": self.survival_doctrine.to_dict(),
            "risk_scale_hint": float(self.risk_scale_hint),
            "advisory_escalation": dict(self.advisory_escalation),
            "diagnostics": dict(self.diagnostics),
        }

    def to_shield_meta(self) -> dict[str, Any]:
        return {
            "execution_intel": {
                "mode": self.mode.value,
                "stress_index": float(self.stress_index.score),
                "execution_quality_score": float(self.quality_estimate.execution_quality_score),
                "expected_total_cost_bps": float(self.quality_estimate.expected_total_cost_bps),
                "expected_net_edge_bps": float(self.quality_estimate.expected_net_edge_bps),
                "abort": bool(self.abort_decision.should_abort),
                "abort_reasons": list(self.abort_decision.reason_codes),
                "latency_degraded": bool(self.latency_drift.degraded),
                "matching_engine_anomaly": bool(self.matching_engine_anomaly.anomaly_flag),
                "api_health_degraded": bool(self.api_health.degraded),
                "withdrawal_liquidity_risk": bool(self.withdrawal_liquidity_risk.risk_flag),
                "spoof_like_oscillation": bool(self.spoofing_heuristic.spoof_like_flag),
            },
            "execution_advisory": dict(self.advisory_escalation),
            "execution_survival_doctrine": self.survival_doctrine.to_dict(),
            "risk_scale": float(self.risk_scale_hint),
            "regime_confidence": _clamp(1.0 - self.stress_index.score, 0.0, 1.0),
        }

    def feedback_metrics(self) -> dict[str, float]:
        return {
            "fill_quality_score": float(self.quality_estimate.expected_fill_quality),
            "timing_error_score": float(_clamp(self.stress_index.score * 0.80 + self.adverse_selection.probability * 0.20, 0.0, 1.0)),
            "realized_vs_expected_slippage": float(self.slippage_impact.expected_slippage_bps),
            "opportunity_decay_metric": float(_clamp(self.stress_index.score * 0.60 + (1.0 - self.fill_uncertainty.lower_bound) * 0.40, 0.0, 1.0)),
        }


class ExecutionIntelligenceEngine:
    """Phase 9 execution intelligence layer refining raw execution plans."""

    def evaluate(
        self,
        *,
        proposal: StrategyProposal,
        baseline_plan: ExecutionPlan,
        world: WorldStateSnapshot,
        mission: MissionDecision,
        learning_summary: Mapping[str, Any] | None = None,
    ) -> ExecutionDecisionEnvelope:
        feedback = self._learning_feedback(learning_summary)
        shield_escalation_signal = self._shield_escalation_signal(world=world, mission=mission)
        if not baseline_plan.actionable:
            mode = ExecutionPersonalityMode.STEALTH_PASSIVE
            empty_slicer = DynamicOrderSlicer(slicing_mode="none", slice_count=0, slice_interval_s=0.0, participation_rate=0.0, slices=[])
            shape = OrderBookShapeModel(
                spread_bps=max(0.0, world.market_state.spread_bps),
                depth_notional=max(0.0, world.market_state.depth_notional),
                participation_ratio=0.0,
                order_flow_imbalance=world.market_state.order_flow_aggression,
                thin_book=world.market_state.liquidity_regime == "THIN",
                wide_spread=world.market_state.spread_bps >= 35.0,
                sudden_depth_drop=False,
            )
            slippage = SlippageImpactEstimator(
                expected_slippage_bps=0.0,
                impact_risk=0.0,
                fee_drag_bps=0.0,
                spread_cross_cost_bps=0.0,
                expected_total_cost_bps=0.0,
            )
            quality = ExecutionQualityEstimate(
                expected_fill_quality=1.0,
                expected_total_cost_bps=0.0,
                expected_net_edge_bps=0.0,
                execution_quality_score=1.0,
            )
            spoofing = SpoofLikeDepthOscillationHeuristic(oscillation_score=0.0, spoof_like_flag=False, oscillation_direction="none")
            survival_doctrine = CapitalSurvivalDoctrine(
                protocol="GradualDeRiskLadder",
                gradual_derisk=GradualDeRiskLadder(steps=(0.25, 0.25, 0.25, 0.25), step_interval_s=6.0, stop_if_recovered=True),
                bounded_execution_loss_quote=0.0,
                replay_safe_signature="GradualDeRiskLadder:non_actionable",
            )
            advisory = self._advisory_escalation(
                mode=mode,
                stress_index=ExecutionStressIndex(score=0.0, spread_breathing=0.0, micro_vol_burst=0.0, liquidity_vacuum=0.0, toxicity=0.0),
                api_health=APIErrorRateHealthScore(health_score=1.0, degraded=False),
                latency_drift=ExchangeLatencyDriftMonitor(latency_ms=world.execution_state.latency_ms, drift_score=0.0, degraded=False),
                matching=MatchingEngineAnomalySignal(anomaly_score=0.0, anomaly_flag=False),
                withdrawal=WithdrawalLiquidityRiskFlag(risk_score=0.0, risk_flag=False),
                spoofing=spoofing,
                abort=ExecutionAbortDecision(should_abort=False, reason_codes=("non_actionable_proposal",)),
                survival_doctrine=survival_doctrine,
            )
            return ExecutionDecisionEnvelope(
                mode=mode,
                plan=baseline_plan,
                order_book_shape=shape,
                slippage_impact=slippage,
                elasticity_curve=ExecutionElasticityCurve(slope=0.0, curvature=0.0, elasticity_band="none"),
                queue_estimate=QueuePositionEstimator(queue_quality=1.0, expected_queue_rank=0.0, queue_decay_risk=0.0, fill_probability_estimate=1.0),
                slicer=empty_slicer,
                stress_index=ExecutionStressIndex(score=0.0, spread_breathing=0.0, micro_vol_burst=0.0, liquidity_vacuum=0.0, toxicity=0.0),
                spoofing_heuristic=spoofing,
                fill_uncertainty=FillUncertaintyEnvelope(expected_fill_probability=1.0, lower_bound=1.0, upper_bound=1.0),
                adverse_selection=AdverseSelectionProbabilityModel(probability=0.0, risk_flag=False),
                capital_at_fill_risk=CapitalAtFillRisk(capital_at_fill_risk_quote=0.0, risk_ratio_to_edge=0.0),
                latency_drift=ExchangeLatencyDriftMonitor(latency_ms=world.execution_state.latency_ms, drift_score=0.0, degraded=False),
                matching_engine_anomaly=MatchingEngineAnomalySignal(anomaly_score=0.0, anomaly_flag=False),
                withdrawal_liquidity_risk=WithdrawalLiquidityRiskFlag(risk_score=0.0, risk_flag=False),
                api_health=APIErrorRateHealthScore(health_score=1.0, degraded=False),
                quality_estimate=quality,
                abort_decision=ExecutionAbortDecision(should_abort=False, reason_codes=("non_actionable_proposal",)),
                survival_doctrine=survival_doctrine,
                risk_scale_hint=1.0,
                advisory_escalation=advisory,
                diagnostics={"reason": "baseline_non_actionable", "shield_escalation_signal": shield_escalation_signal},
            )

        target_notional = max(0.0, baseline_plan.target_notional_quote)
        depth = max(1.0, world.market_state.depth_notional)
        participation = _clamp(target_notional / depth, 0.0, 5.0)
        shape = OrderBookShapeModel(
            spread_bps=max(0.0, world.market_state.spread_bps),
            depth_notional=max(0.0, world.market_state.depth_notional),
            participation_ratio=participation,
            order_flow_imbalance=_clamp(world.market_state.order_flow_aggression, -1.0, 1.0),
            thin_book=world.market_state.liquidity_regime == "THIN" or world.market_state.depth_notional < 1_200.0,
            wide_spread=world.market_state.spread_bps >= 25.0,
            sudden_depth_drop=(
                world.market_state.depth_notional < 900.0
                and (
                    world.execution_state.execution_stress >= 0.45
                    or world.execution_state.rejection_ratio >= 0.25
                )
            ),
        )

        spread_breathing = SpreadBreathingAnalyzer(
            stress_score=_clamp((shape.spread_bps / 18.0) + (abs(shape.order_flow_imbalance) * 0.20), 0.0, 1.0),
            breathing_flag=shape.spread_bps >= 25.0,
        )
        micro_vol_burst = MicroVolatilityBurstDetector(
            stress_score=_clamp((world.market_state.realized_vol / 0.015) + (abs(world.market_state.trend_bias_bps) / 220.0), 0.0, 1.0),
            burst_flag=world.market_state.realized_vol >= 0.018,
        )
        liquidity_vacuum = LiquidityVacuumDetector(
            stress_score=_clamp((1.0 - min(shape.depth_notional / 15_000.0, 1.0)) + (shape.participation_ratio * 0.80), 0.0, 1.0),
            vacuum_flag=shape.thin_book or shape.sudden_depth_drop,
        )
        spoofing = self._spoof_like_depth_oscillation(
            shape=shape,
            world=world,
            spread_breathing=spread_breathing,
            micro_vol_burst=micro_vol_burst,
        )
        toxicity = OrderFlowToxicityHeuristic(
            toxicity_score=_clamp(
                (world.execution_state.rejection_ratio * 1.40)
                + ((1.0 - world.execution_state.fill_probability) * 0.60)
                + (abs(shape.order_flow_imbalance) * 0.20),
                0.0,
                1.0,
            ),
            toxic_flag=world.execution_state.rejection_ratio >= 0.20 or spoofing.spoof_like_flag,
        )
        toxicity = OrderFlowToxicityHeuristic(
            toxicity_score=_clamp(
                toxicity.toxicity_score + (spoofing.oscillation_score * 0.22),
                0.0,
                1.0,
            ),
            toxic_flag=toxicity.toxic_flag,
        )
        stress_index = ExecutionStressIndex(
            score=_clamp(
                (spread_breathing.stress_score * 0.20)
                + (micro_vol_burst.stress_score * 0.22)
                + (liquidity_vacuum.stress_score * 0.28)
                + (toxicity.toxicity_score * 0.22)
                + (spoofing.oscillation_score * 0.08),
                0.0,
                1.0,
            ),
            spread_breathing=spread_breathing.stress_score,
            micro_vol_burst=micro_vol_burst.stress_score,
            liquidity_vacuum=liquidity_vacuum.stress_score,
            toxicity=toxicity.toxicity_score,
        )
        memory_pressure = self._memory_pressure(feedback)

        mode = self._select_mode(
            mission=mission,
            proposal=proposal,
            stress_index=stress_index,
            shape=shape,
            world=world,
            learning_feedback=feedback,
            shield_escalation_signal=shield_escalation_signal,
            spoofing=spoofing,
        )

        queue_estimate = self._queue_position(
            world=world,
            baseline_plan=baseline_plan,
            mode=mode,
            stress_index=stress_index,
        )
        slippage = self._slippage_impact(
            world=world,
            baseline_plan=baseline_plan,
            shape=shape,
            mode=mode,
            stress_index=stress_index,
        )
        elasticity = self._elasticity_curve(shape=shape, slippage=slippage, target_notional=target_notional)
        slicer = self._dynamic_slicer(
            mode=mode,
            target_notional=target_notional,
            max_slippage_bps=slippage.expected_slippage_bps,
            participation=shape.participation_ratio,
            stress_index=stress_index,
            spoofing=spoofing,
        )

        fill_uncertainty = self._fill_uncertainty(world=world, stress_index=stress_index, queue=queue_estimate)
        adverse = self._adverse_selection(
            side=proposal.side,
            shape=shape,
            stress_index=stress_index,
            fill_uncertainty=fill_uncertainty,
        )

        latency_drift = self._latency_drift(world=world)
        matching_anomaly = self._matching_engine_signal(world=world, stress_index=stress_index)
        withdrawal_risk = self._withdrawal_liquidity_risk(world=world, stress_index=stress_index)
        api_health = self._api_health_score(world=world)

        size_scale = self._size_scale(
            mode=mode,
            stress_index=stress_index,
            shape=shape,
            fill_uncertainty=fill_uncertainty,
            learning_feedback=feedback,
            shield_escalation_signal=shield_escalation_signal,
            spoofing=spoofing,
        )
        adjusted_notional = max(0.0, target_notional * size_scale)
        reference_price = max(world.market_state.last_mid, 1e-9)
        adjusted_size = adjusted_notional / reference_price

        expected_edge_bps = max(0.0, proposal.expected_value_bps)
        expected_net_edge_bps = expected_edge_bps - slippage.expected_total_cost_bps
        quality = ExecutionQualityEstimate(
            expected_fill_quality=fill_uncertainty.expected_fill_probability,
            expected_total_cost_bps=slippage.expected_total_cost_bps,
            expected_net_edge_bps=expected_net_edge_bps,
            execution_quality_score=_clamp(
                (fill_uncertainty.expected_fill_probability * 0.40)
                + ((1.0 - stress_index.score) * 0.35)
                + ((1.0 - adverse.probability) * 0.25),
                0.0,
                1.0,
            ),
        )
        edge_quote = max(1e-6, adjusted_notional * max(expected_edge_bps, 0.01) / 10_000.0)
        capital_risk = CapitalAtFillRisk(
            capital_at_fill_risk_quote=adjusted_notional * ((slippage.expected_slippage_bps + adverse.probability * 10.0) / 10_000.0),
            risk_ratio_to_edge=_clamp(
                (adjusted_notional * ((slippage.expected_total_cost_bps + adverse.probability * 10.0) / 10_000.0)) / edge_quote,
                0.0,
                50.0,
            ),
        )
        survival_doctrine = self._capital_survival_doctrine(
            mode=mode,
            withdrawal=withdrawal_risk,
            liquidity_vacuum=liquidity_vacuum,
            matching=matching_anomaly,
            target_notional=adjusted_notional,
            stress_index=stress_index,
        )

        abort = self._abort_decision(
            quality=quality,
            stress=stress_index,
            slippage=slippage,
            capital_risk=capital_risk,
            api_health=api_health,
            latency_drift=latency_drift,
            matching=matching_anomaly,
            withdrawal=withdrawal_risk,
            shield_escalation_signal=shield_escalation_signal,
            spoofing=spoofing,
        )

        urgency = self._urgency_for(mode=mode, stress_index=stress_index)
        maker_taker = self._maker_taker_for(mode=mode, shape=shape, stress_index=stress_index)
        order_type = self._order_type_for(maker_taker, mode)
        timeout_budget = self._timeout_budget(mode=mode, proposal=proposal)
        risk_scale_hint = _clamp(1.0 - (stress_index.score * 0.50) - (shield_escalation_signal * 0.15), 0.10, 1.0)

        feedback_metrics = {
            "fill_quality_score": quality.expected_fill_quality,
            "timing_error_score": _clamp(stress_index.score * 0.80 + adverse.probability * 0.20, 0.0, 1.0),
            "realized_vs_expected_slippage": slippage.expected_slippage_bps,
            "opportunity_decay_metric": _clamp(stress_index.score * 0.60 + (1.0 - fill_uncertainty.lower_bound) * 0.40, 0.0, 1.0),
        }
        advisory = self._advisory_escalation(
            mode=mode,
            stress_index=stress_index,
            api_health=api_health,
            latency_drift=latency_drift,
            matching=matching_anomaly,
            withdrawal=withdrawal_risk,
            spoofing=spoofing,
            abort=abort,
            survival_doctrine=survival_doctrine,
        )
        execution_meta = {
            "phase": "phase9_execution_intelligence",
            "mode": mode.value,
            "order_book_shape": shape.to_dict(),
            "slippage_impact": slippage.to_dict(),
            "elasticity_curve": elasticity.to_dict(),
            "queue_estimate": queue_estimate.to_dict(),
            "slicer": slicer.to_dict(),
            "stress_index": stress_index.to_dict(),
            "spoofing_heuristic": spoofing.to_dict(),
            "fill_uncertainty": fill_uncertainty.to_dict(),
            "adverse_selection": adverse.to_dict(),
            "capital_at_fill_risk": capital_risk.to_dict(),
            "latency_drift": latency_drift.to_dict(),
            "matching_engine_anomaly": matching_anomaly.to_dict(),
            "withdrawal_liquidity_risk": withdrawal_risk.to_dict(),
            "api_health": api_health.to_dict(),
            "quality": quality.to_dict(),
            "abort": abort.to_dict(),
            "feedback_metrics": feedback_metrics,
            "survival_protocol": survival_doctrine.to_dict(),
            "advisory_escalation": advisory,
            "shield_escalation_signal": shield_escalation_signal,
            "memory_pressure": memory_pressure,
            "inference_markers": [
                "heuristic:order_book_shape",
                "heuristic:stress_index",
                "heuristic:fill_uncertainty",
                "heuristic:adverse_selection",
                "heuristic:spoof_like_depth_oscillation",
            ],
        }
        plan = replace(
            baseline_plan,
            target_notional_quote=adjusted_notional,
            target_size=adjusted_size,
            max_slippage_bps=max(0.5, min(75.0, slippage.expected_slippage_bps + 1.0)),
            maker_taker=maker_taker,
            order_type=order_type,
            urgency_tier=urgency,
            timeout_s=timeout_budget,
            cancel_replace_budget=max(1, 3 + slicer.slice_count),
            queue_quality=queue_estimate.queue_quality,
            expected_fill_quality=quality.expected_fill_quality,
            slice_count=slicer.slice_count,
            slice_interval_s=slicer.slice_interval_s,
            fee_drag_estimate_bps=slippage.fee_drag_bps,
            expected_net_edge_bps=quality.expected_net_edge_bps,
            execution_quality_estimate=quality.to_dict(),
            meta={
                **dict(baseline_plan.meta),
                "execution_intelligence": execution_meta,
                "execution_personality_mode": mode.value,
                "execution_feedback_metrics": feedback_metrics,
                "execution_advisory": advisory,
            },
        )
        if abort.should_abort:
            reason = abort.reason_codes[0] if abort.reason_codes else "execution_abort"
            plan = plan.as_non_actionable(reason)
            plan = replace(
                plan,
                meta={
                    **dict(plan.meta),
                    "execution_intelligence": execution_meta,
                    "execution_personality_mode": mode.value,
                    "execution_feedback_metrics": feedback_metrics,
                    "execution_advisory": advisory,
                    "abort_reason_codes": list(abort.reason_codes),
                },
            )

        diagnostics = {
            "mode": mode.value,
            "stress_score": stress_index.score,
            "spoof_like_oscillation_score": spoofing.oscillation_score,
            "expected_total_cost_bps": quality.expected_total_cost_bps,
            "expected_net_edge_bps": quality.expected_net_edge_bps,
            "risk_scale_hint": risk_scale_hint,
            "shield_escalation_signal": shield_escalation_signal,
            "memory_pressure": memory_pressure,
            "abort": abort.should_abort,
            "abort_reason_codes": list(abort.reason_codes),
            "size_scale": size_scale,
            "advisory": advisory,
        }
        return ExecutionDecisionEnvelope(
            mode=mode,
            plan=plan,
            order_book_shape=shape,
            slippage_impact=slippage,
            elasticity_curve=elasticity,
            queue_estimate=queue_estimate,
            slicer=slicer,
            stress_index=stress_index,
            spoofing_heuristic=spoofing,
            fill_uncertainty=fill_uncertainty,
            adverse_selection=adverse,
            capital_at_fill_risk=capital_risk,
            latency_drift=latency_drift,
            matching_engine_anomaly=matching_anomaly,
            withdrawal_liquidity_risk=withdrawal_risk,
            api_health=api_health,
            quality_estimate=quality,
            abort_decision=abort,
            survival_doctrine=survival_doctrine,
            risk_scale_hint=risk_scale_hint,
            advisory_escalation=advisory,
            diagnostics=diagnostics,
        )

    def _select_mode(
        self,
        *,
        mission: MissionDecision,
        proposal: StrategyProposal,
        stress_index: ExecutionStressIndex,
        shape: OrderBookShapeModel,
        world: WorldStateSnapshot,
        learning_feedback: Mapping[str, float],
        shield_escalation_signal: float,
        spoofing: SpoofLikeDepthOscillationHeuristic,
    ) -> ExecutionPersonalityMode:
        memory_pressure = self._memory_pressure(learning_feedback)
        posture = str(mission.execution_posture_hint or "normal").strip().lower()
        shield_hint = str(mission.shield_posture_hint or "normal").strip().lower()
        if (
            proposal.side == "sell"
            and (
                mission.mission in {"risk_off_defense", "inventory_unwind", "preserve_capital"}
                or posture in {"risk_off", "de_risk", "inventory_unwind"}
                or shield_hint in {"hard_defensive", "observe-only"}
            )
            and (
                world.portfolio_state.drawdown_pct >= 0.06
                or stress_index.score >= 0.55
                or shield_escalation_signal >= 0.65
            )
        ):
            return ExecutionPersonalityMode.PANIC_EXIT
        if (
            stress_index.score >= 0.75
            or world.infra_state.system_health_stress >= 0.65
            or shield_escalation_signal >= 0.80
            or memory_pressure >= 0.80
            or spoofing.spoof_like_flag
        ):
            return ExecutionPersonalityMode.STEALTH_PASSIVE
        if (
            mission.mission == "momentum_extraction"
            and stress_index.score <= 0.35
            and shield_escalation_signal <= 0.30
            and memory_pressure <= 0.45
            and not shape.thin_book
            and not shape.wide_spread
            and posture in {"aggressive_if_quality", "balanced", "normal"}
        ):
            return ExecutionPersonalityMode.AGGRESSIVE_CAPTURE
        if (
            world.market_state.liquidity_regime == "DEEP"
            and world.market_state.spread_bps <= 8.0
            and world.execution_state.queue_quality >= 0.75
            and shield_escalation_signal <= 0.45
            and memory_pressure <= 0.55
            and not spoofing.spoof_like_flag
        ):
            return ExecutionPersonalityMode.LIQUIDITY_SNIPER
        return ExecutionPersonalityMode.BALANCED_ALPHA

    def _queue_position(
        self,
        *,
        world: WorldStateSnapshot,
        baseline_plan: ExecutionPlan,
        mode: ExecutionPersonalityMode,
        stress_index: ExecutionStressIndex,
    ) -> QueuePositionEstimator:
        queue_quality = _clamp(world.execution_state.queue_quality, 0.0, 1.0)
        if mode in {ExecutionPersonalityMode.STEALTH_PASSIVE, ExecutionPersonalityMode.LIQUIDITY_SNIPER}:
            queue_quality = _clamp(queue_quality + 0.08, 0.0, 1.0)
        if mode in {ExecutionPersonalityMode.AGGRESSIVE_CAPTURE, ExecutionPersonalityMode.PANIC_EXIT}:
            queue_quality = _clamp(queue_quality - 0.12, 0.0, 1.0)
        fill_probability_estimate = _clamp(
            (world.execution_state.fill_probability * 0.50)
            + (queue_quality * 0.30)
            + ((1.0 - stress_index.score) * 0.20),
            0.01,
            1.0,
        )
        if baseline_plan.maker_taker == "taker":
            fill_probability_estimate = _clamp(fill_probability_estimate + 0.12, 0.01, 1.0)
        expected_queue_rank = _clamp(1.0 - queue_quality, 0.0, 1.0)
        queue_decay_risk = _clamp((1.0 - queue_quality) * 0.60 + stress_index.score * 0.40, 0.0, 1.0)
        return QueuePositionEstimator(
            queue_quality=queue_quality,
            expected_queue_rank=expected_queue_rank,
            queue_decay_risk=queue_decay_risk,
            fill_probability_estimate=fill_probability_estimate,
        )

    def _slippage_impact(
        self,
        *,
        world: WorldStateSnapshot,
        baseline_plan: ExecutionPlan,
        shape: OrderBookShapeModel,
        mode: ExecutionPersonalityMode,
        stress_index: ExecutionStressIndex,
    ) -> SlippageImpactEstimator:
        maker_bias = 1.0 if baseline_plan.maker_taker == "maker" else 0.0
        if mode in {ExecutionPersonalityMode.STEALTH_PASSIVE, ExecutionPersonalityMode.LIQUIDITY_SNIPER}:
            maker_bias = 1.0
        elif mode in {ExecutionPersonalityMode.AGGRESSIVE_CAPTURE, ExecutionPersonalityMode.PANIC_EXIT}:
            maker_bias = 0.0

        base_slippage = (
            shape.spread_bps * (0.16 if maker_bias > 0.5 else 0.42)
            + shape.participation_ratio * 26.0
            + world.execution_state.execution_stress * 8.0
            + stress_index.score * 9.0
        )
        expected_slippage = _clamp(base_slippage, 0.1, 120.0)
        impact_risk = _clamp((shape.participation_ratio * 0.55) + (stress_index.score * 0.35) + (expected_slippage / 80.0), 0.0, 1.0)
        # final_edge_bps from strategy proposals is already typically cost-aware, so this layer applies
        # incremental execution drag only (not full fee schedule replay) to avoid double-penalizing entries.
        fee_drag = 1.5 if maker_bias > 0.5 else 3.0
        spread_cross = shape.spread_bps * (0.08 if maker_bias > 0.5 else 0.25)
        expected_total_cost = expected_slippage + fee_drag + spread_cross + (_clamp(world.execution_state.latency_ms / 1_000.0, 0.0, 1.0) * 1.2)
        return SlippageImpactEstimator(
            expected_slippage_bps=expected_slippage,
            impact_risk=impact_risk,
            fee_drag_bps=fee_drag,
            spread_cross_cost_bps=spread_cross,
            expected_total_cost_bps=expected_total_cost,
        )

    def _elasticity_curve(
        self,
        *,
        shape: OrderBookShapeModel,
        slippage: SlippageImpactEstimator,
        target_notional: float,
    ) -> ExecutionElasticityCurve:
        base_size = max(target_notional, 1.0)
        slope = _clamp(slippage.expected_slippage_bps / base_size, 0.0, 1.0)
        curvature = _clamp((shape.participation_ratio ** 2) + (slippage.impact_risk * 0.25), 0.0, 2.0)
        if curvature >= 1.0:
            band = "convex"
        elif curvature >= 0.35:
            band = "linear_plus"
        else:
            band = "linear"
        return ExecutionElasticityCurve(slope=slope, curvature=curvature, elasticity_band=band)

    def _dynamic_slicer(
        self,
        *,
        mode: ExecutionPersonalityMode,
        target_notional: float,
        max_slippage_bps: float,
        participation: float,
        stress_index: ExecutionStressIndex,
        spoofing: SpoofLikeDepthOscillationHeuristic,
    ) -> DynamicOrderSlicer:
        if target_notional <= 0.0:
            return DynamicOrderSlicer(slicing_mode="none", slice_count=0, slice_interval_s=0.0, participation_rate=0.0, slices=[])

        if mode == ExecutionPersonalityMode.PANIC_EXIT:
            slicing_mode = "pov"
            slice_count = max(2, min(8, int(2 + participation * 8)))
            interval = 1.2
        elif mode == ExecutionPersonalityMode.STEALTH_PASSIVE:
            slicing_mode = "twap"
            slice_count = max(3, min(12, int(3 + participation * 10)))
            interval = 6.0
        elif mode == ExecutionPersonalityMode.LIQUIDITY_SNIPER:
            slicing_mode = "hybrid"
            slice_count = max(2, min(5, int(2 + participation * 4)))
            interval = 2.0
        elif mode == ExecutionPersonalityMode.AGGRESSIVE_CAPTURE:
            slicing_mode = "pov"
            slice_count = max(1, min(3, int(1 + participation * 3)))
            interval = 1.0
        else:
            slicing_mode = "hybrid"
            slice_count = max(2, min(6, int(2 + participation * 5)))
            interval = 3.0

        unstable_microstructure = stress_index.score >= 0.55 or spoofing.spoof_like_flag
        if unstable_microstructure:
            interval *= 1.40
            if mode in {ExecutionPersonalityMode.BALANCED_ALPHA, ExecutionPersonalityMode.STEALTH_PASSIVE}:
                slice_count = min(14, max(2, slice_count + 1))

        slice_notional = target_notional / max(slice_count, 1)
        slices: list[ExecutionSlice] = []
        for idx in range(slice_count):
            weight = 1.0
            if slicing_mode == "pov" and mode == ExecutionPersonalityMode.PANIC_EXIT:
                weight = 1.20 if idx == 0 else 0.90
            if unstable_microstructure and mode != ExecutionPersonalityMode.PANIC_EXIT:
                # Delay or clip early fills when microstructure is unstable.
                weight = 0.85 if idx == 0 else 1.05
            weighted_notional = max(0.0, slice_notional * weight)
            slices.append(
                ExecutionSlice(
                    idx=idx + 1,
                    notional_quote=weighted_notional,
                    wait_s=interval,
                    max_slippage_bps=max_slippage_bps,
                )
            )
        total = sum(row.notional_quote for row in slices)
        if total > 0.0:
            scale = target_notional / total
            slices = [
                ExecutionSlice(
                    idx=row.idx,
                    notional_quote=row.notional_quote * scale,
                    wait_s=row.wait_s,
                    max_slippage_bps=row.max_slippage_bps,
                )
                for row in slices
            ]
        return DynamicOrderSlicer(
            slicing_mode=slicing_mode,
            slice_count=slice_count,
            slice_interval_s=interval,
            participation_rate=_clamp(
                participation
                * _clamp(1.0 - (stress_index.score * 0.28) - (spoofing.oscillation_score * 0.20), 0.30, 1.0),
                0.0,
                5.0,
            ),
            slices=slices,
        )

    def _fill_uncertainty(
        self,
        *,
        world: WorldStateSnapshot,
        stress_index: ExecutionStressIndex,
        queue: QueuePositionEstimator,
    ) -> FillUncertaintyEnvelope:
        expected = _clamp(queue.fill_probability_estimate, 0.01, 1.0)
        spread = _clamp(0.08 + (stress_index.score * 0.35), 0.02, 0.60)
        return FillUncertaintyEnvelope(
            expected_fill_probability=expected,
            lower_bound=_clamp(expected - spread, 0.0, 1.0),
            upper_bound=_clamp(expected + spread, 0.0, 1.0),
        )

    def _adverse_selection(
        self,
        *,
        side: str,
        shape: OrderBookShapeModel,
        stress_index: ExecutionStressIndex,
        fill_uncertainty: FillUncertaintyEnvelope,
    ) -> AdverseSelectionProbabilityModel:
        align = 0.0
        if side == "buy":
            align = -0.05 if shape.order_flow_imbalance > 0 else 0.07
        elif side == "sell":
            align = -0.05 if shape.order_flow_imbalance < 0 else 0.07
        probability = _clamp(
            0.18 + (stress_index.score * 0.45) + ((1.0 - fill_uncertainty.lower_bound) * 0.20) + align,
            0.0,
            1.0,
        )
        return AdverseSelectionProbabilityModel(probability=probability, risk_flag=probability >= 0.65)

    def _latency_drift(self, *, world: WorldStateSnapshot) -> ExchangeLatencyDriftMonitor:
        latency = max(0.0, world.execution_state.latency_ms)
        drift = _clamp((latency - 60.0) / 350.0 + world.infra_state.system_health_stress * 0.30, 0.0, 1.0)
        return ExchangeLatencyDriftMonitor(latency_ms=latency, drift_score=drift, degraded=drift >= 0.60)

    def _matching_engine_signal(self, *, world: WorldStateSnapshot, stress_index: ExecutionStressIndex) -> MatchingEngineAnomalySignal:
        anomaly = _clamp(
            (world.execution_state.rejection_ratio * 1.40)
            + ((1.0 - world.execution_state.queue_quality) * 0.35)
            + (0.20 if world.infra_state.desync else 0.0)
            + (stress_index.score * 0.20),
            0.0,
            1.0,
        )
        return MatchingEngineAnomalySignal(anomaly_score=anomaly, anomaly_flag=anomaly >= 0.70)

    def _withdrawal_liquidity_risk(self, *, world: WorldStateSnapshot, stress_index: ExecutionStressIndex) -> WithdrawalLiquidityRiskFlag:
        risk = _clamp(
            (0.45 if world.infra_state.stale_feed else 0.0)
            + (0.35 if world.infra_state.desync else 0.0)
            + world.infra_state.system_health_stress * 0.30
            + stress_index.score * 0.20,
            0.0,
            1.0,
        )
        return WithdrawalLiquidityRiskFlag(risk_score=risk, risk_flag=risk >= 0.75)

    def _api_health_score(self, *, world: WorldStateSnapshot) -> APIErrorRateHealthScore:
        error_pressure = _clamp((world.execution_state.rejection_ratio * 1.40) + world.infra_state.system_health_stress * 0.40, 0.0, 1.0)
        health = _clamp(1.0 - error_pressure, 0.0, 1.0)
        return APIErrorRateHealthScore(health_score=health, degraded=health <= 0.45)

    def _learning_feedback(self, learning_summary: Mapping[str, Any] | None) -> dict[str, float]:
        payload = dict(learning_summary or {})
        feedback = payload.get("execution_feedback_summary", {})
        if not isinstance(feedback, Mapping):
            return {
                "fill_quality_score": 0.7,
                "timing_error_score": 0.3,
                "realized_vs_expected_slippage": 2.0,
                "opportunity_decay_metric": 0.3,
            }
        return {
            "fill_quality_score": _clamp(_safe_float(feedback.get("fill_quality_score", 0.7), 0.7), 0.0, 1.0),
            "timing_error_score": _clamp(_safe_float(feedback.get("timing_error_score", 0.3), 0.3), 0.0, 1.0),
            "realized_vs_expected_slippage": max(0.0, _safe_float(feedback.get("realized_vs_expected_slippage", 2.0), 2.0)),
            "opportunity_decay_metric": _clamp(_safe_float(feedback.get("opportunity_decay_metric", 0.3), 0.3), 0.0, 1.0),
        }

    def _memory_pressure(self, learning_feedback: Mapping[str, float]) -> float:
        return _clamp(
            (_safe_float(learning_feedback.get("timing_error_score", 0.3), 0.3) * 0.45)
            + (_safe_float(learning_feedback.get("opportunity_decay_metric", 0.3), 0.3) * 0.35)
            + (min(_safe_float(learning_feedback.get("realized_vs_expected_slippage", 2.0), 2.0) / 30.0, 1.0) * 0.20),
            0.0,
            1.0,
        )

    def _shield_escalation_signal(self, *, world: WorldStateSnapshot, mission: MissionDecision) -> float:
        risk_mode_map = {
            "normal": 0.0,
            "cautious": 0.35,
            "defensive": 0.65,
            "observe_only": 0.90,
            "hard_stop": 1.0,
        }
        posture_map = {
            "normal": 0.0,
            "cautious": 0.35,
            "defensive": 0.65,
            "hard_defensive": 0.85,
            "observe-only": 0.90,
        }
        risk_mode = str(world.risk_state.mode or "normal").strip().lower()
        mission_posture = str(mission.shield_posture_hint or "normal").strip().lower()
        base = max(
            risk_mode_map.get(risk_mode, 0.30),
            posture_map.get(mission_posture, 0.20),
            0.40 if not mission.allow_new_risk else 0.0,
        )
        return _clamp(base + (world.infra_state.system_health_stress * 0.20), 0.0, 1.0)

    def _spoof_like_depth_oscillation(
        self,
        *,
        shape: OrderBookShapeModel,
        world: WorldStateSnapshot,
        spread_breathing: SpreadBreathingAnalyzer,
        micro_vol_burst: MicroVolatilityBurstDetector,
    ) -> SpoofLikeDepthOscillationHeuristic:
        queue_fill_dislocation = _clamp(world.execution_state.queue_quality - world.execution_state.fill_probability, 0.0, 1.0)
        depth_fragility = _clamp(1.0 - min(shape.depth_notional / 2_500.0, 1.0), 0.0, 1.0)
        score = _clamp(
            (depth_fragility * 0.32)
            + (spread_breathing.stress_score * 0.20)
            + (queue_fill_dislocation * 0.30)
            + (abs(shape.order_flow_imbalance) * 0.10)
            + (micro_vol_burst.stress_score * 0.08),
            0.0,
            1.0,
        )
        direction = "none"
        if spread_breathing.breathing_flag and shape.order_flow_imbalance > 0.20:
            direction = "ask_pull"
        elif spread_breathing.breathing_flag and shape.order_flow_imbalance < -0.20:
            direction = "bid_pull"
        elif spread_breathing.breathing_flag:
            direction = "mixed"
        spoof_like = score >= 0.62 and (shape.wide_spread or queue_fill_dislocation >= 0.25)
        return SpoofLikeDepthOscillationHeuristic(
            oscillation_score=score,
            spoof_like_flag=spoof_like,
            oscillation_direction=direction,
        )

    def _size_scale(
        self,
        *,
        mode: ExecutionPersonalityMode,
        stress_index: ExecutionStressIndex,
        shape: OrderBookShapeModel,
        fill_uncertainty: FillUncertaintyEnvelope,
        learning_feedback: Mapping[str, float],
        shield_escalation_signal: float,
        spoofing: SpoofLikeDepthOscillationHeuristic,
    ) -> float:
        scale = 1.0
        scale *= _clamp(1.0 - stress_index.score * 0.45, 0.20, 1.0)
        scale *= _clamp(1.0 - shape.participation_ratio * 0.35, 0.30, 1.0)
        scale *= _clamp(fill_uncertainty.lower_bound + 0.20, 0.35, 1.0)
        scale *= _clamp(1.0 - _safe_float(learning_feedback.get("timing_error_score", 0.3), 0.3) * 0.25, 0.70, 1.0)
        scale *= _clamp(1.0 - _safe_float(learning_feedback.get("opportunity_decay_metric", 0.3), 0.3) * 0.20, 0.75, 1.0)
        scale *= _clamp(1.0 - (shield_escalation_signal * 0.45), 0.30, 1.0)
        scale *= _clamp(1.0 - (spoofing.oscillation_score * 0.35), 0.35, 1.0)
        if mode == ExecutionPersonalityMode.AGGRESSIVE_CAPTURE:
            scale *= 1.10
        elif mode == ExecutionPersonalityMode.LIQUIDITY_SNIPER:
            scale *= 0.95
        elif mode == ExecutionPersonalityMode.STEALTH_PASSIVE:
            scale *= 0.75
        elif mode == ExecutionPersonalityMode.PANIC_EXIT:
            scale *= 1.00
        if spoofing.spoof_like_flag and mode in {ExecutionPersonalityMode.BALANCED_ALPHA, ExecutionPersonalityMode.AGGRESSIVE_CAPTURE}:
            scale *= 0.75
        return _clamp(scale, 0.10, 1.15)

    def _abort_decision(
        self,
        *,
        quality: ExecutionQualityEstimate,
        stress: ExecutionStressIndex,
        slippage: SlippageImpactEstimator,
        capital_risk: CapitalAtFillRisk,
        api_health: APIErrorRateHealthScore,
        latency_drift: ExchangeLatencyDriftMonitor,
        matching: MatchingEngineAnomalySignal,
        withdrawal: WithdrawalLiquidityRiskFlag,
        shield_escalation_signal: float,
        spoofing: SpoofLikeDepthOscillationHeuristic,
    ) -> ExecutionAbortDecision:
        reasons: list[str] = []
        if quality.expected_net_edge_bps <= 0.0:
            reasons.append("no_net_edge_after_costs")
        if stress.score >= 0.92:
            reasons.append("execution_stress_extreme")
        if slippage.impact_risk >= 0.90:
            reasons.append("impact_risk_exceeds_threshold")
        if capital_risk.risk_ratio_to_edge > 3.00:
            reasons.append("fill_risk_exceeds_alpha_edge")
        if spoofing.spoof_like_flag and slippage.impact_risk >= 0.80:
            reasons.append("spoof_like_liquidity_instability")
        if api_health.degraded and (latency_drift.degraded or matching.anomaly_flag):
            reasons.append("exchange_health_degraded")
        if withdrawal.risk_flag and (stress.score >= 0.65 or shield_escalation_signal >= 0.75):
            reasons.append("systemic_venue_risk")
        if shield_escalation_signal >= 0.85 and quality.expected_net_edge_bps <= 1.0:
            reasons.append("shield_escalation_overrides_marginal_edge")
        return ExecutionAbortDecision(should_abort=bool(reasons), reason_codes=tuple(reasons))

    def _urgency_for(self, *, mode: ExecutionPersonalityMode, stress_index: ExecutionStressIndex) -> str:
        if mode in {ExecutionPersonalityMode.PANIC_EXIT, ExecutionPersonalityMode.AGGRESSIVE_CAPTURE}:
            return "high"
        if mode == ExecutionPersonalityMode.STEALTH_PASSIVE:
            return "low"
        if stress_index.score >= 0.65:
            return "low"
        return "normal"

    def _maker_taker_for(
        self,
        mode: ExecutionPersonalityMode,
        *,
        shape: OrderBookShapeModel,
        stress_index: ExecutionStressIndex,
    ) -> str:
        if mode in {ExecutionPersonalityMode.PANIC_EXIT, ExecutionPersonalityMode.AGGRESSIVE_CAPTURE}:
            return "taker"
        if mode == ExecutionPersonalityMode.STEALTH_PASSIVE and not shape.wide_spread:
            return "maker"
        if stress_index.score >= 0.70 and shape.wide_spread:
            return "maker"
        return "maker" if shape.spread_bps <= 10.0 else "taker"

    def _order_type_for(self, maker_taker: str, mode: ExecutionPersonalityMode) -> str:
        if maker_taker == "maker":
            return "post_only" if mode in {ExecutionPersonalityMode.STEALTH_PASSIVE, ExecutionPersonalityMode.LIQUIDITY_SNIPER} else "limit"
        return "ioc" if mode in {ExecutionPersonalityMode.AGGRESSIVE_CAPTURE, ExecutionPersonalityMode.PANIC_EXIT} else "marketable_limit"

    def _timeout_budget(self, *, mode: ExecutionPersonalityMode, proposal: StrategyProposal) -> float:
        hold = max(5.0, float(proposal.expected_hold_time_s))
        if mode == ExecutionPersonalityMode.PANIC_EXIT:
            return min(8.0, hold * 0.10)
        if mode == ExecutionPersonalityMode.AGGRESSIVE_CAPTURE:
            return min(12.0, hold * 0.20)
        if mode == ExecutionPersonalityMode.STEALTH_PASSIVE:
            return min(45.0, hold * 0.55)
        if mode == ExecutionPersonalityMode.LIQUIDITY_SNIPER:
            return min(25.0, hold * 0.35)
        return min(30.0, hold * 0.40)

    def _capital_survival_doctrine(
        self,
        *,
        mode: ExecutionPersonalityMode,
        withdrawal: WithdrawalLiquidityRiskFlag,
        liquidity_vacuum: LiquidityVacuumDetector,
        matching: MatchingEngineAnomalySignal,
        target_notional: float,
        stress_index: ExecutionStressIndex,
    ) -> CapitalSurvivalDoctrine:
        target = max(0.0, float(target_notional))
        if mode == ExecutionPersonalityMode.PANIC_EXIT:
            panic = PanicFlattenProtocol(
                max_loss_bps=40.0,
                slice_weights=(0.45, 0.35, 0.20),
                ioc_timeout_s=2.0,
                allow_cross_spread=True,
            )
            recovery = (
                FrozenOrderRecoveryRoutine(max_recovery_attempts=3, cancel_backoff_s=1.0, force_taker_after_attempts=2)
                if matching.anomaly_flag
                else None
            )
            return CapitalSurvivalDoctrine(
                protocol="PanicFlattenProtocol",
                panic_flatten=panic,
                frozen_order_recovery=recovery,
                bounded_execution_loss_quote=target * (panic.max_loss_bps / 10_000.0),
                replay_safe_signature=f"PanicFlattenProtocol:{round(target, 4)}:{int(matching.anomaly_flag)}",
            )
        if withdrawal.risk_flag:
            recovery = FrozenOrderRecoveryRoutine(max_recovery_attempts=5, cancel_backoff_s=2.5, force_taker_after_attempts=3)
            ladder = GradualDeRiskLadder(steps=(0.40, 0.30, 0.30), step_interval_s=4.0, stop_if_recovered=False)
            return CapitalSurvivalDoctrine(
                protocol="FrozenOrderRecoveryRoutine",
                frozen_order_recovery=recovery,
                gradual_derisk=ladder,
                bounded_execution_loss_quote=target * (35.0 / 10_000.0),
                replay_safe_signature=f"FrozenOrderRecoveryRoutine:{round(target, 4)}",
            )
        if liquidity_vacuum.vacuum_flag:
            crash = LiquidityCrashExitStrategy(
                cliff_depth_threshold_quote=1_000.0,
                max_participation_rate=0.22,
                emergency_slippage_cap_bps=_clamp(22.0 + stress_index.score * 18.0, 22.0, 45.0),
            )
            recovery = (
                FrozenOrderRecoveryRoutine(max_recovery_attempts=4, cancel_backoff_s=1.6, force_taker_after_attempts=2)
                if matching.anomaly_flag
                else None
            )
            return CapitalSurvivalDoctrine(
                protocol="LiquidityCrashExitStrategy",
                liquidity_crash_exit=crash,
                frozen_order_recovery=recovery,
                bounded_execution_loss_quote=target * (crash.emergency_slippage_cap_bps / 10_000.0),
                replay_safe_signature=f"LiquidityCrashExitStrategy:{round(target, 4)}:{round(crash.emergency_slippage_cap_bps, 2)}",
            )
        ladder = GradualDeRiskLadder(steps=(0.25, 0.25, 0.25, 0.25), step_interval_s=8.0, stop_if_recovered=True)
        return CapitalSurvivalDoctrine(
            protocol="GradualDeRiskLadder",
            gradual_derisk=ladder,
            frozen_order_recovery=FrozenOrderRecoveryRoutine(max_recovery_attempts=3, cancel_backoff_s=2.0, force_taker_after_attempts=3)
            if matching.anomaly_flag
            else None,
            bounded_execution_loss_quote=target * (18.0 / 10_000.0),
            replay_safe_signature=f"GradualDeRiskLadder:{round(target, 4)}",
        )

    def _advisory_escalation(
        self,
        *,
        mode: ExecutionPersonalityMode,
        stress_index: ExecutionStressIndex,
        api_health: APIErrorRateHealthScore,
        latency_drift: ExchangeLatencyDriftMonitor,
        matching: MatchingEngineAnomalySignal,
        withdrawal: WithdrawalLiquidityRiskFlag,
        spoofing: SpoofLikeDepthOscillationHeuristic,
        abort: ExecutionAbortDecision,
        survival_doctrine: CapitalSurvivalDoctrine,
    ) -> dict[str, Any]:
        severity_score = _clamp(
            (stress_index.score * 0.35)
            + ((1.0 - api_health.health_score) * 0.25)
            + (latency_drift.drift_score * 0.15)
            + (matching.anomaly_score * 0.10)
            + (withdrawal.risk_score * 0.10)
            + (spoofing.oscillation_score * 0.05),
            0.0,
            1.0,
        )
        if abort.should_abort:
            severity_score = max(severity_score, 0.90)
        reason_codes: list[str] = []
        if stress_index.score >= 0.65:
            reason_codes.append("execution_stress_rising")
        if api_health.degraded:
            reason_codes.append("api_health_degraded")
        if latency_drift.degraded:
            reason_codes.append("latency_drift_degraded")
        if matching.anomaly_flag:
            reason_codes.append("matching_engine_anomaly")
        if withdrawal.risk_flag:
            reason_codes.append("withdrawal_liquidity_risk")
        if spoofing.spoof_like_flag:
            reason_codes.append("spoof_like_depth_oscillation")
        if abort.should_abort:
            reason_codes.extend(str(code) for code in abort.reason_codes)
        deduped = tuple(dict.fromkeys(reason_codes).keys())
        if severity_score >= 0.85:
            severity = "critical"
            recommended_shield_mode = "hard_stop"
        elif severity_score >= 0.65:
            severity = "high"
            recommended_shield_mode = "observe_only"
        elif severity_score >= 0.40:
            severity = "elevated"
            recommended_shield_mode = "defensive"
        else:
            severity = "normal"
            recommended_shield_mode = "normal"
        return {
            "severity": severity,
            "severity_score": float(severity_score),
            "reason_codes": list(deduped),
            "recommended_shield_mode": recommended_shield_mode,
            "requires_manual_review": bool(severity in {"critical", "high"}),
            "mode": mode.value,
            "survival_protocol": survival_doctrine.protocol,
        }
