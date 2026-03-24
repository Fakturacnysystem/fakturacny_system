from __future__ import annotations

from datetime import datetime
from typing import Any

from autonomous_investment_robot.core.contracts import SyntheticAffectState


class SyntheticAffectEngine:
    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        forecast: Any,
        regime_assessment: Any,
        execution_quality: Any,
        inventory_state: Any | None,
        reserve_state: Any | None,
        quantum_state: Any | None,
        edge_immunity_decision: Any | None,
        event_intelligence: Any | None,
    ) -> SyntheticAffectState:
        confidence = float(getattr(forecast, "confidence", 0.0) or 0.0)
        regime_conf = float(getattr(regime_assessment, "confidence", 0.0) or 0.0)
        fill_prob = float(getattr(execution_quality, "fill_probability", 0.0) or 0.0)
        adverse = float(getattr(execution_quality, "adverse_selection_risk", 0.0) or 0.0)
        stale_score = 0.0 if inventory_state is None else float(getattr(inventory_state, "stale_inventory_score", 0.0) or 0.0)
        reserve_breach = False if reserve_state is None else bool(getattr(reserve_state, "reserve_breached", False))
        event_risk = 0.0 if event_intelligence is None else float(getattr(event_intelligence, "overall_risk_score", 0.0) or 0.0)
        fragility = 0.0
        uncertainty = 0.0
        if edge_immunity_decision is not None:
            fragility = float(getattr(getattr(edge_immunity_decision, "report", None), "fragility_index", 0.0) or 0.0)
        if quantum_state is not None:
            uncertainty = float(getattr(getattr(quantum_state, "collapse_decision", None), "uncertainty", 0.0) or 0.0)

        stress = max(0.0, min(1.0, 0.3 * fragility + 0.2 * adverse + 0.2 * event_risk + 0.15 * stale_score + (0.15 if reserve_breach else 0.0)))
        caution = max(0.0, min(1.0, 0.35 * uncertainty + 0.25 * (1.0 - fill_prob) + 0.2 * event_risk + 0.2 * stale_score))
        conviction = max(0.0, min(1.0, 0.45 * confidence + 0.35 * regime_conf + 0.2 * max(0.0, 1.0 - uncertainty)))
        fear = max(0.0, min(1.0, 0.45 * event_risk + 0.3 * fragility + 0.25 * (1.0 - fill_prob)))
        asymmetry = max(0.0, min(1.0, 0.5 * max(confidence - uncertainty, 0.0) + 0.5 * max(1.0 - adverse, 0.0)))
        aggression_clamp = max(0.0, min(1.0, 1.0 - 0.5 * stress - 0.35 * caution - 0.25 * fear + 0.2 * conviction))
        threshold_shift = max(0.0, min(0.4, 0.2 * stress + 0.15 * caution + 0.15 * fear))
        recommended_action = "continue"
        reasons: list[str] = []
        if stress >= 0.8 or fear >= 0.8:
            recommended_action = "no_trade"
            reasons.append("stress_or_fear_extreme")
            aggression_clamp = 0.0
        elif caution >= 0.65 or fragility >= 0.55:
            recommended_action = "trade_smaller"
            reasons.append("caution_or_fragility_elevated")
            aggression_clamp = min(aggression_clamp, 0.5)
        elif conviction >= 0.7 and asymmetry >= 0.55 and stress < 0.4:
            recommended_action = "controlled_expand"
            reasons.append("confidence_and_conviction_support")
            aggression_clamp = min(1.0, max(aggression_clamp, 0.85))

        return SyntheticAffectState(
            symbol=symbol,
            ts=ts,
            confidence_state=confidence,
            caution=caution,
            stress=stress,
            conviction=conviction,
            fear=fear,
            asymmetry=asymmetry,
            aggression_clamp=aggression_clamp,
            no_trade_threshold_shift=threshold_shift,
            recommended_action=recommended_action,
            reasons=reasons,
            partial=event_intelligence is None,
            metadata={
                "fill_probability": fill_prob,
                "adverse_selection_risk": adverse,
                "stale_inventory_score": stale_score,
                "reserve_breach": reserve_breach,
                "fragility": fragility,
                "uncertainty": uncertainty,
            },
        )
