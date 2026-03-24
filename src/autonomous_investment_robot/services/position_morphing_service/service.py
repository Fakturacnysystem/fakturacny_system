from __future__ import annotations

from datetime import datetime
from typing import Any

from autonomous_investment_robot.core.contracts import PositionMorphPlan


class PositionMorphingEngine:
    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        current_exposure: float,
        capital_sovereignty: Any,
        synthetic_affect: Any | None,
        quantum_state: Any | None,
        edge_immunity_decision: Any | None,
    ) -> PositionMorphPlan:
        exposure = abs(float(current_exposure))
        action = str(getattr(capital_sovereignty, "action", "continue"))
        stress = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "stress", 0.0) or 0.0)
        conviction = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "conviction", 0.0) or 0.0)
        fear = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "fear", 0.0) or 0.0)
        fragility = 0.0
        if edge_immunity_decision is not None:
            fragility = float(getattr(getattr(edge_immunity_decision, "report", None), "fragility_index", 0.0) or 0.0)
        dominant_state = ""
        if quantum_state is not None:
            dominant_state = str(getattr(getattr(quantum_state, "scenario_tree", None), "dominant_state", "") or "")

        core_fraction = float(getattr(capital_sovereignty, "keep_core_ratio", 0.7) or 0.7)
        satellite_fraction = float(getattr(capital_sovereignty, "satellite_ratio", 0.3) or 0.3)
        runner_fraction = 0.0
        add_notional = 0.0
        reduce_notional = 0.0
        probe_notional = 0.0
        keep_core = True
        trim_satellites = False
        allow_runner = False
        reduce_risk = False
        reasons: list[str] = []

        if action in {"release", "rotate", "wait", "no_trade"}:
            trim_satellites = exposure > 0.0
            reduce_risk = exposure > 0.0
            reduce_notional = exposure * max(0.0, satellite_fraction)
            reasons.append(f"capital_action:{action}")
        if action == "probe_only":
            probe_notional = max(0.0, float(getattr(capital_sovereignty, "probe_ratio", 0.0) or 0.0))
            add_notional = probe_notional
            reasons.append("probe_entry_only")
        if dominant_state in {"bullish_continuation", "squeeze"} and conviction >= 0.55 and fragility < 0.45 and action == "continue":
            allow_runner = True
            runner_fraction = min(0.25, 0.1 + 0.2 * conviction)
            reasons.append("runner_allowed")
        if stress >= 0.65 or fear >= 0.65 or fragility >= 0.6:
            reduce_risk = True
            trim_satellites = True
            runner_fraction = 0.0
            reasons.append("risk_compression")
        if action == "no_trade":
            keep_core = exposure > 0.0 and core_fraction > 0.0
            add_notional = 0.0
            probe_notional = 0.0

        partial = quantum_state is None and synthetic_affect is None
        if partial:
            reasons.append("partial_morph_context")

        return PositionMorphPlan(
            symbol=symbol,
            ts=ts,
            action=action,
            keep_core=keep_core,
            trim_satellites=trim_satellites,
            allow_runner=allow_runner,
            reduce_risk=reduce_risk,
            core_fraction=max(0.0, min(1.0, core_fraction)),
            satellite_fraction=max(0.0, min(1.0, satellite_fraction)),
            runner_fraction=max(0.0, min(1.0, runner_fraction)),
            add_notional=max(0.0, add_notional),
            reduce_notional=max(0.0, reduce_notional),
            probe_notional=max(0.0, probe_notional),
            reasons=reasons,
            partial=partial,
            metadata={
                "dominant_state": dominant_state,
                "stress": stress,
                "conviction": conviction,
                "fear": fear,
                "fragility": fragility,
            },
        )
