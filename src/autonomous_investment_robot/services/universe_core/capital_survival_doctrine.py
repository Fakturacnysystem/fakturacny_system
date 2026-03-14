from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .adaptive_personality_engine import PersonalityTrace
from .cross_reality_signal import CrossRealitySignal
from .market_energy_physics import MarketEnergyState


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class ExchangeFailureRisk:
    venue: str
    failure_probability: float
    withdrawal_risk: float
    confidence: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue": self.venue,
            "failure_probability": float(self.failure_probability),
            "withdrawal_risk": float(self.withdrawal_risk),
            "confidence": float(self.confidence),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class SystemicCollapseState:
    collapse_risk: float
    liquidity_freeze_risk: float
    contagion_score: float
    confidence: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "collapse_risk": float(self.collapse_risk),
            "liquidity_freeze_risk": float(self.liquidity_freeze_risk),
            "contagion_score": float(self.contagion_score),
            "confidence": float(self.confidence),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class ExistentialRiskSignal:
    level: str
    score: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "score": float(self.score),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class CapitalBunkerDecision:
    activate: bool
    cash_reserve_ratio: float
    hedge_ratio: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activate": bool(self.activate),
            "cash_reserve_ratio": float(self.cash_reserve_ratio),
            "hedge_ratio": float(self.hedge_ratio),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class SurvivalDoctrineDecision:
    existential_risk: ExistentialRiskSignal
    exchange_failure: ExchangeFailureRisk
    systemic_collapse: SystemicCollapseState
    capital_bunker: CapitalBunkerDecision
    recommendation_mode: str
    safety_veto: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "existential_risk": self.existential_risk.to_dict(),
            "exchange_failure": self.exchange_failure.to_dict(),
            "systemic_collapse": self.systemic_collapse.to_dict(),
            "capital_bunker": self.capital_bunker.to_dict(),
            "recommendation_mode": self.recommendation_mode,
            "safety_veto": bool(self.safety_veto),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


class CapitalSurvivalDoctrine:
    """Phase 32 survival-first escalation model (advisory, fail-closed)."""

    def assess(
        self,
        *,
        world: Any,
        energy: MarketEnergyState,
        cross_reality: CrossRealitySignal,
        personality: PersonalityTrace,
        integrity_escalation: Mapping[str, Any] | None = None,
    ) -> SurvivalDoctrineDecision:
        infra = getattr(world, "infra_state", None)
        market = getattr(world, "market_state", None)
        venue = str(getattr(getattr(world, "venue_state", None), "primary_venue", "unknown") or "unknown")
        outage_risk = 0.15
        reasons: list[str] = []
        integrity = _safe_mapping(integrity_escalation)
        integrity_fail_closed = bool(integrity.get("fail_closed", False))
        integrity_mode = str(integrity.get("recommended_mode", "") or "")
        integrity_scale = _clamp(_safe_float(integrity.get("confidence_scale", 1.0), 1.0), 0.0, 1.0)
        integrity_reasons = integrity.get("escalation_reason_codes", [])
        if integrity_fail_closed:
            reasons.append("cross_reality_integrity_fail_closed")
        elif integrity_mode == "observe_only":
            reasons.append("cross_reality_integrity_observe_only")
        if bool(getattr(infra, "stale_feed", False)):
            outage_risk += 0.30
            reasons.append("stale_feed")
        if bool(getattr(infra, "desync", False)):
            outage_risk += 0.35
            reasons.append("venue_desync")
        outage_risk += cross_reality.composite_pressure * 0.20
        if integrity_fail_closed:
            outage_risk += 0.40
        elif integrity_mode == "observe_only":
            outage_risk += 0.20
        exchange_failure = ExchangeFailureRisk(
            venue=venue,
            failure_probability=_clamp(outage_risk, 0.0, 1.0),
            withdrawal_risk=_clamp(cross_reality.derivatives.pressure_score * 0.40 + cross_reality.social.panic_score * 0.60, 0.0, 1.0),
            confidence=_clamp((cross_reality.confidence + (1.0 - energy.instability.instability_score)) / 2.0, 0.05, 1.0),
            reason_codes=tuple(reasons),
        )
        panic = 1.0 if bool(getattr(market, "panic", False)) else 0.0
        systemic = SystemicCollapseState(
            collapse_risk=_clamp(energy.instability.instability_score * 0.40 + cross_reality.composite_pressure * 0.45 + panic * 0.15, 0.0, 1.0),
            liquidity_freeze_risk=_clamp(energy.friction.coefficient * 0.60 + cross_reality.vol_surface.deformation_score * 0.40, 0.0, 1.0),
            contagion_score=_clamp(cross_reality.social.panic_score * 0.45 + cross_reality.on_chain.pressure_score * 0.35 + exchange_failure.failure_probability * 0.20, 0.0, 1.0),
            confidence=_clamp(((cross_reality.integrity.component_coverage + cross_reality.confidence) / 2.0) * integrity_scale, 0.05, 1.0),
            reason_codes=tuple(["systemic_model_v1"]),
        )
        personality_survival = 0.0
        if bool(getattr(personality.constraints, "hard_safety_override", False)):
            personality_survival = 1.0
        elif personality.risk_personality.value == "survival":
            personality_survival = 0.75
        existential_score = _clamp(
            exchange_failure.failure_probability * 0.30
            + systemic.collapse_risk * 0.30
            + systemic.liquidity_freeze_risk * 0.15
            + personality_survival * 0.25,
            0.0,
            1.0,
        )
        level = "extreme" if existential_score >= 0.80 else "high" if existential_score >= 0.60 else "elevated" if existential_score >= 0.45 else "normal"
        if integrity_fail_closed and level not in {"extreme", "high"}:
            level = "high"
        existential = ExistentialRiskSignal(
            level=level,
            score=existential_score,
            reason_codes=tuple(["capital_survival_doctrine"]),
        )
        bunker = CapitalBunkerDecision(
            activate=bool(level in {"extreme", "high"}),
            cash_reserve_ratio=0.85 if level == "extreme" else 0.65 if level == "high" else 0.40 if level == "elevated" else 0.20,
            hedge_ratio=0.90 if level == "extreme" else 0.70 if level == "high" else 0.40 if level == "elevated" else 0.15,
            reason_codes=tuple(["survival_escalation" if level in {"extreme", "high"} else "normal_mode"]),
        )
        veto = bool(level in {"extreme", "high"} or bool(getattr(personality.constraints, "hard_safety_override", False)))
        recommendation_mode = "survival" if veto else "defensive" if level == "elevated" else "normal"
        summary_reasons = [f"existential_level:{level}"]
        if isinstance(integrity_reasons, list):
            summary_reasons.extend([f"integrity:{str(item)}" for item in integrity_reasons if str(item)])
        if veto:
            summary_reasons.append("safety_veto_active")
        return SurvivalDoctrineDecision(
            existential_risk=existential,
            exchange_failure=exchange_failure,
            systemic_collapse=systemic,
            capital_bunker=bunker,
            recommendation_mode=recommendation_mode,
            safety_veto=veto,
            reason_codes=tuple(summary_reasons),
        )
