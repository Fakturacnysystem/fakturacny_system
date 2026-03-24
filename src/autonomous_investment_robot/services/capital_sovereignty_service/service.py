from __future__ import annotations

from datetime import datetime
from typing import Any

from autonomous_investment_robot.core.contracts import CapitalSovereigntyDecision


class CapitalSovereigntyService:
    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        reserve_state: Any | None,
        inventory_state: Any | None,
        portfolio_allocation: Any | None,
        round_trip: dict[str, Any] | None,
        event_intelligence: Any | None,
        synthetic_affect: Any | None,
        quantum_state: Any | None,
        edge_immunity_decision: Any | None,
    ) -> CapitalSovereigntyDecision:
        reserve_pct = 1.0 if reserve_state is None else float(getattr(reserve_state, "free_quote_reserve_pct", 1.0))
        reserve_breach = False if reserve_state is None else bool(getattr(reserve_state, "reserve_breached", False))
        stale_score = 0.0 if inventory_state is None else float(getattr(inventory_state, "stale_inventory_score", 0.0))
        opportunity = 0.0 if portfolio_allocation is None else float(getattr(portfolio_allocation, "opportunity_cost_score", 0.0))
        gross_open = 0.0 if inventory_state is None else float(getattr(inventory_state, "gross_open_notional", 0.0))
        net_edge = 0.0 if round_trip is None else float(round_trip.get("net_edge_bps", 0.0) or 0.0)
        round_trip_action = "trade_now" if round_trip is None else str(round_trip.get("action", "trade_now"))
        event_risk = 0.0 if event_intelligence is None else float(getattr(event_intelligence, "overall_risk_score", 0.0) or 0.0)
        event_action = "continue" if event_intelligence is None else str(getattr(event_intelligence, "recommended_action", "continue"))
        stress = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "stress", 0.0) or 0.0)
        fear = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "fear", 0.0) or 0.0)
        affect_multiplier = 1.0 if synthetic_affect is None else float(getattr(synthetic_affect, "aggression_clamp", 1.0) or 1.0)
        fragility = 0.0
        if edge_immunity_decision is not None:
            fragility = float(getattr(getattr(edge_immunity_decision, "report", None), "fragility_index", 0.0) or 0.0)
        uncertainty = 0.0
        if quantum_state is not None:
            uncertainty = float(getattr(getattr(quantum_state, "collapse_decision", None), "uncertainty", 0.0) or 0.0)

        freedom_envelope = max(0.0, min(1.0, reserve_pct * (1.0 - 0.45 * stale_score) * (1.0 - 0.35 * fragility) * (1.0 - 0.25 * event_risk)))
        rotation_score = max(0.0, min(1.0, 0.55 * opportunity + 0.45 * stale_score))
        keep_core_ratio = max(0.0, min(1.0, 0.7 - 0.35 * stress - 0.25 * fear + 0.15 * max(net_edge, 0.0) / 25.0))
        satellite_ratio = max(0.0, min(1.0, 1.0 - keep_core_ratio))
        probe_ratio = max(0.0, min(0.35, 0.2 * affect_multiplier * (1.0 - uncertainty)))

        action = "continue"
        reasons: list[str] = []
        size_multiplier = max(0.0, min(1.0, freedom_envelope * affect_multiplier))
        rotate_notional = 0.0
        release_notional = 0.0
        if round_trip_action == "no_trade":
            action = "no_trade"
            reasons.append("round_trip_non_viable")
            size_multiplier = 0.0
        elif event_action == "no_trade":
            action = "no_trade"
            reasons.append("event_intelligence_no_trade")
            size_multiplier = 0.0
        elif reserve_breach and stale_score >= 0.35:
            action = "release"
            reasons.extend(["reserve_breach", "stale_inventory"])
            release_notional = gross_open * min(0.6, max(0.2, stale_score))
            size_multiplier = min(size_multiplier, 0.25)
        elif event_action == "wait" or stress >= 0.75 or fear >= 0.75:
            action = "wait"
            reasons.append("affect_or_event_wait")
            size_multiplier = 0.0
        elif rotation_score >= 0.65 and gross_open > 0.0:
            action = "rotate"
            reasons.append("opportunity_rotation")
            rotate_notional = gross_open * min(0.5, rotation_score)
            size_multiplier = min(size_multiplier, 0.4)
        elif freedom_envelope < 0.35 or fragility >= 0.55:
            action = "probe_only"
            reasons.append("capital_probe_only")
            size_multiplier = min(size_multiplier, 0.3)
        elif reserve_breach:
            action = "trade_smaller"
            reasons.append("reserve_breach")
            size_multiplier = min(size_multiplier, 0.5)

        partial = reserve_state is None or inventory_state is None
        if partial:
            reasons.append("partial_capital_state")

        return CapitalSovereigntyDecision(
            symbol=symbol,
            ts=ts,
            action=action,
            freedom_envelope_score=freedom_envelope,
            reserve_pressure=max(0.0, 1.0 - reserve_pct),
            rotation_score=rotation_score,
            recommended_size_multiplier=size_multiplier,
            keep_core_ratio=keep_core_ratio,
            satellite_ratio=satellite_ratio,
            probe_ratio=probe_ratio,
            release_notional=release_notional,
            rotate_notional=rotate_notional,
            reasons=reasons,
            partial=partial,
            metadata={
                "reserve_pct": reserve_pct,
                "stale_score": stale_score,
                "event_risk": event_risk,
                "stress": stress,
                "fear": fear,
                "fragility": fragility,
                "uncertainty": uncertainty,
                "net_edge_bps": net_edge,
            },
        )
