from __future__ import annotations

from datetime import datetime
from typing import Any

from autonomous_investment_robot.core.contracts import AdaptiveExitAllocation


class AdaptiveExitAllocator:
    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        current_exposure: float,
        capital_release_decision: Any | None,
        position_morph_plan: Any | None,
        synthetic_affect: Any | None,
        event_intelligence: Any | None,
    ) -> AdaptiveExitAllocation:
        exposure = abs(float(current_exposure))
        release_allowed = bool(getattr(capital_release_decision, "allowed", False)) if capital_release_decision is not None else False
        release_notional = 0.0 if capital_release_decision is None else float(getattr(capital_release_decision, "recommended_notional", 0.0) or 0.0)
        reduce_notional = 0.0 if position_morph_plan is None else float(getattr(position_morph_plan, "reduce_notional", 0.0) or 0.0)
        runner_fraction = 0.0 if position_morph_plan is None else float(getattr(position_morph_plan, "runner_fraction", 0.0) or 0.0)
        stress = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "stress", 0.0) or 0.0)
        fear = 0.0 if synthetic_affect is None else float(getattr(synthetic_affect, "fear", 0.0) or 0.0)
        event_action = "continue" if event_intelligence is None else str(getattr(event_intelligence, "recommended_action", "continue"))
        event_risk = 0.0 if event_intelligence is None else float(getattr(event_intelligence, "overall_risk_score", 0.0) or 0.0)

        action = "hold"
        execution_style = "passive_limit"
        total_exit = 0.0
        reasons: list[str] = []

        if release_allowed:
            total_exit = max(total_exit, release_notional)
            action = "partial_exit"
            reasons.append(f"capital_release:{getattr(capital_release_decision, 'reason', 'allowed')}")
        if reduce_notional > 0.0:
            total_exit = max(total_exit, reduce_notional)
            action = "partial_exit"
            reasons.append("position_morph_reduce")
        if event_action == "no_trade" and exposure > 0.0:
            total_exit = max(total_exit, exposure * min(0.75, 0.35 + 0.4 * event_risk))
            action = "risk_exit"
            reasons.append("event_intelligence_exit")
        elif event_action == "wait" and exposure > 0.0:
            total_exit = max(total_exit, exposure * 0.25)
            action = "partial_exit"
            reasons.append("event_wait_de_risk")
        if stress >= 0.75 or fear >= 0.75:
            total_exit = max(total_exit, exposure * 0.5)
            action = "risk_exit"
            execution_style = "marketable_limit"
            reasons.append("affect_compression_exit")

        total_exit = min(exposure, max(0.0, total_exit))
        runner_notional = max(0.0, exposure * runner_fraction)
        satellite_exit = min(total_exit, max(0.0, total_exit - runner_notional))
        core_exit = max(0.0, total_exit - satellite_exit)
        if action in {"risk_exit", "flatten"}:
            execution_style = "marketable_limit"
        elif event_action == "wait":
            execution_style = "passive_limit"

        partial = capital_release_decision is None and position_morph_plan is None
        if partial:
            reasons.append("partial_exit_context")

        return AdaptiveExitAllocation(
            symbol=symbol,
            ts=ts,
            action=action,
            core_exit_notional=core_exit,
            satellite_exit_notional=satellite_exit,
            runner_notional=runner_notional,
            total_exit_notional=total_exit,
            execution_style=execution_style,
            reasons=reasons,
            partial=partial,
            metadata={
                "stress": stress,
                "fear": fear,
                "event_action": event_action,
                "event_risk": event_risk,
                "release_allowed": release_allowed,
            },
        )
