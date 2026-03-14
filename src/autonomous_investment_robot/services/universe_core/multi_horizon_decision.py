from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .global_market_brain import GlobalMarketState


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass(frozen=True)
class MicroDecisionContext:
    urgency_score: float
    liquidity_quality: float
    execution_stress: float
    confidence: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "urgency_score": float(self.urgency_score),
            "liquidity_quality": float(self.liquidity_quality),
            "execution_stress": float(self.execution_stress),
            "confidence": float(self.confidence),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class TacticalDecisionContext:
    alpha_conviction: float
    regime_fit: float
    opportunity_score: float
    confidence: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha_conviction": float(self.alpha_conviction),
            "regime_fit": float(self.regime_fit),
            "opportunity_score": float(self.opportunity_score),
            "confidence": float(self.confidence),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class StrategicDecisionContext:
    allocation_bias: str
    risk_budget_scale: float
    capital_preservation_bias: float
    confidence: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allocation_bias": self.allocation_bias,
            "risk_budget_scale": float(self.risk_budget_scale),
            "capital_preservation_bias": float(self.capital_preservation_bias),
            "confidence": float(self.confidence),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class StructuralRegimeContext:
    structural_regime: str
    systemic_risk: float
    macro_pressure: float
    confidence: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "structural_regime": self.structural_regime,
            "systemic_risk": float(self.systemic_risk),
            "macro_pressure": float(self.macro_pressure),
            "confidence": float(self.confidence),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class CrossHorizonConflict:
    horizon_a: str
    horizon_b: str
    severity: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_a": self.horizon_a,
            "horizon_b": self.horizon_b,
            "severity": float(self.severity),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class HorizonAlignmentReport:
    micro: MicroDecisionContext
    tactical: TacticalDecisionContext
    strategic: StrategicDecisionContext
    structural: StructuralRegimeContext
    alignment_score: float
    dominant_horizon: str
    recommendation_safe: bool
    conflicts: list[CrossHorizonConflict] = field(default_factory=list)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "micro": self.micro.to_dict(),
            "tactical": self.tactical.to_dict(),
            "strategic": self.strategic.to_dict(),
            "structural": self.structural.to_dict(),
            "alignment_score": float(self.alignment_score),
            "dominant_horizon": self.dominant_horizon,
            "recommendation_safe": bool(self.recommendation_safe),
            "conflicts": [row.to_dict() for row in self.conflicts],
            "reason_codes": [str(item) for item in self.reason_codes],
        }


class MultiHorizonDecisionLayer:
    """Phase 27 typed horizon diagnostics with explicit conflict detection."""

    def assess(
        self,
        *,
        world: Any,
        global_market: GlobalMarketState,
        mission: Any,
        verdict: Any,
        plan: Any,
    ) -> HorizonAlignmentReport:
        market = getattr(world, "market_state", None)
        execution = getattr(world, "execution_state", None)
        portfolio = getattr(world, "portfolio_state", None)
        micro = MicroDecisionContext(
            urgency_score=_clamp(
                _safe_float(getattr(plan, "urgency_alpha", 0.0), 0.0)
                + _safe_float(getattr(execution, "execution_stress", 0.0), 0.0) * 0.50,
                0.0,
                1.0,
            ),
            liquidity_quality=_clamp(1.0 - _safe_float(getattr(market, "spread_bps", 0.0), 0.0) / 120.0, 0.0, 1.0),
            execution_stress=_clamp(_safe_float(getattr(execution, "execution_stress", 0.0), 0.0), 0.0, 1.0),
            confidence=_clamp(0.70 * global_market.confidence.overall + 0.30 * (1.0 - global_market.market_stress), 0.0, 1.0),
            reason_codes=tuple(["micro_execution_focus"]),
        )
        selected = getattr(verdict, "selected", None)
        tactical = TacticalDecisionContext(
            alpha_conviction=_clamp(_safe_float(getattr(selected, "confidence", 0.0), 0.0), 0.0, 1.0),
            regime_fit=_clamp(_safe_float(getattr(selected, "regime_compatibility", 0.0), 0.0), 0.0, 1.0),
            opportunity_score=_clamp(_safe_float(getattr(selected, "expected_value_bps", 0.0), 0.0) / 30.0, 0.0, 1.0),
            confidence=_clamp(global_market.confidence.overall * 0.60 + (1.0 - global_market.partial_data) * 0.40, 0.0, 1.0),
            reason_codes=tuple(["tactical_alpha_context"]),
        )
        drawdown = _safe_float(getattr(portfolio, "drawdown_pct", 0.0), 0.0)
        strategic = StrategicDecisionContext(
            allocation_bias="defensive" if global_market.market_stress >= 0.65 or drawdown >= 0.08 else "balanced" if global_market.risk_on_score >= 0.40 else "risk_off",
            risk_budget_scale=_clamp((1.0 - global_market.market_stress) * (1.0 - min(drawdown / 0.20, 1.0)), 0.0, 1.0),
            capital_preservation_bias=_clamp(max(global_market.market_stress, min(drawdown / 0.15, 1.0)), 0.0, 1.0),
            confidence=_clamp((global_market.confidence.overall + tactical.confidence) / 2.0, 0.0, 1.0),
            reason_codes=tuple(["strategic_allocation_context"]),
        )
        structural = StructuralRegimeContext(
            structural_regime="fragile" if global_market.market_stress >= 0.70 else "transitional" if global_market.market_stress >= 0.45 else "stable",
            systemic_risk=_clamp(
                global_market.market_stress * 0.55
                + global_market.cross_venue.venue_outage_risk * 0.25
                + global_market.sentiment.panic_index * 0.20,
                0.0,
                1.0,
            ),
            macro_pressure=_clamp(
                global_market.macro_liquidity.policy_tightness * 0.50
                + global_market.macro_liquidity.funding_pressure * 0.50,
                0.0,
                1.0,
            ),
            confidence=_clamp(global_market.confidence.overall, 0.0, 1.0),
            reason_codes=tuple(["structural_regime_context"]),
        )

        conflicts: list[CrossHorizonConflict] = []
        if micro.urgency_score >= 0.75 and strategic.risk_budget_scale <= 0.35:
            conflicts.append(
                CrossHorizonConflict(
                    horizon_a="micro",
                    horizon_b="strategic",
                    severity=_clamp((micro.urgency_score - strategic.risk_budget_scale), 0.0, 1.0),
                    reason_codes=("urgent_execution_vs_low_risk_budget",),
                )
            )
        if tactical.opportunity_score >= 0.70 and structural.systemic_risk >= 0.70:
            conflicts.append(
                CrossHorizonConflict(
                    horizon_a="tactical",
                    horizon_b="structural",
                    severity=_clamp((tactical.opportunity_score + structural.systemic_risk) / 2.0, 0.0, 1.0),
                    reason_codes=("alpha_opportunity_vs_systemic_risk",),
                )
            )
        alignment_seed = (
            micro.confidence * 0.25
            + tactical.confidence * 0.30
            + strategic.confidence * 0.25
            + structural.confidence * 0.20
        )
        conflict_penalty = sum(row.severity for row in conflicts) * 0.35
        alignment_score = _clamp(alignment_seed - conflict_penalty, 0.0, 1.0)
        dominant_horizon = "structural" if structural.systemic_risk >= 0.70 else "tactical" if tactical.opportunity_score >= micro.urgency_score else "micro"
        recommendation_safe = bool(alignment_score >= 0.35 and not global_market.partial_data)
        reason_codes: list[str] = []
        if conflicts:
            reason_codes.append("cross_horizon_conflicts_detected")
        if global_market.partial_data:
            reason_codes.append("global_market_context_partial")
        if not recommendation_safe:
            reason_codes.append("recommendation_not_safe")
        return HorizonAlignmentReport(
            micro=micro,
            tactical=tactical,
            strategic=strategic,
            structural=structural,
            alignment_score=alignment_score,
            dominant_horizon=dominant_horizon,
            recommendation_safe=recommendation_safe,
            conflicts=conflicts,
            reason_codes=tuple(reason_codes),
        )
