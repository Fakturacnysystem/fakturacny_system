from __future__ import annotations

from datetime import datetime
from typing import Any

from autonomous_investment_robot.core.contracts import ExecutionSimulationReport, ExecutionSimulationScenario


class ExecutionSimulationSandbox:
    def simulate(
        self,
        *,
        symbol: str,
        ts: datetime,
        intent: Any,
        snapshot: Any,
        execution_quality: Any,
        expected_edge_bps: float,
        market_integrity: Any | None = None,
        venue_limit_decision: Any | None = None,
        synthetic_affect: Any | None = None,
    ) -> ExecutionSimulationReport:
        fill_prob = float(getattr(execution_quality, "fill_probability", 0.0) or 0.0)
        adverse = float(getattr(execution_quality, "adverse_selection_risk", 0.0) or 0.0)
        spread_bps = float(getattr(snapshot, "spread_bps", 0.0) or 0.0)
        market_action = "continue" if market_integrity is None else str(getattr(market_integrity, "action", "continue"))
        affect_clamp = 1.0 if synthetic_affect is None else float(getattr(synthetic_affect, "aggression_clamp", 1.0) or 1.0)
        scenarios = [
            ExecutionSimulationScenario(
                name="baseline",
                fill_probability=fill_prob,
                expected_slippage_bps=max(0.0, spread_bps * 0.35 + adverse * 2.0),
                expected_cost_bps=max(0.0, spread_bps * 0.55 + adverse * 3.0),
                recommended_action="continue",
                reasons=["baseline_execution_path"],
            ),
            ExecutionSimulationScenario(
                name="wide_spread",
                fill_probability=max(0.0, fill_prob * 0.7),
                expected_slippage_bps=max(0.0, spread_bps * 1.25 + adverse * 3.0),
                expected_cost_bps=max(0.0, spread_bps * 1.8 + adverse * 3.5),
                recommended_action="trade_smaller",
                reasons=["wide_spread_stress"],
            ),
            ExecutionSimulationScenario(
                name="thin_book",
                fill_probability=max(0.0, fill_prob * 0.55),
                expected_slippage_bps=max(0.0, spread_bps * 0.9 + adverse * 4.0),
                expected_cost_bps=max(0.0, spread_bps * 1.3 + adverse * 5.0),
                recommended_action="wait",
                reasons=["thin_book_partial_fill_risk"],
            ),
            ExecutionSimulationScenario(
                name="latency_partial_fill",
                fill_probability=max(0.0, fill_prob * 0.45),
                expected_slippage_bps=max(0.0, spread_bps * 0.8 + adverse * 5.0),
                expected_cost_bps=max(0.0, spread_bps * 1.2 + adverse * 6.0),
                recommended_action="no_trade",
                reasons=["latency_partial_fill_breaks_edge"],
            ),
        ]
        expected_slippage = sum(item.expected_slippage_bps for item in scenarios) / len(scenarios)
        stressed_fill = min(item.fill_probability for item in scenarios)
        worst_cost = max(item.expected_cost_bps for item in scenarios)
        recommended_action = "continue"
        recommended_execution_style = "passive_limit"
        reasons: list[str] = []
        if market_action in {"halt", "flatten_only"}:
            recommended_action = "no_trade"
            reasons.append("market_integrity_blocks_execution")
        elif worst_cost >= max(expected_edge_bps, 0.0) or stressed_fill <= 0.2:
            recommended_action = "no_trade"
            reasons.append("execution_sandbox_breaks_edge")
        elif stressed_fill <= 0.4 or affect_clamp <= 0.5:
            recommended_action = "trade_smaller"
            reasons.append("execution_sandbox_trade_smaller")
        elif worst_cost >= max(expected_edge_bps * 0.7, 3.0):
            recommended_action = "wait"
            reasons.append("execution_sandbox_wait")
        if recommended_action in {"no_trade", "wait"}:
            recommended_execution_style = "passive_limit"
        elif stressed_fill < fill_prob * 0.75:
            recommended_execution_style = "iceberg_passive"
        if venue_limit_decision is not None and bool(getattr(venue_limit_decision, "reduce_only_only", False)):
            recommended_action = "no_trade"
            reasons.append("venue_limit_reduce_only")
        return ExecutionSimulationReport(
            symbol=symbol,
            ts=ts,
            recommended_action=recommended_action,
            recommended_execution_style=recommended_execution_style,
            expected_fill_probability=fill_prob,
            stressed_fill_probability=stressed_fill,
            expected_slippage_bps=expected_slippage,
            worst_case_cost_bps=worst_cost,
            scenarios=scenarios,
            reasons=sorted(set(reasons)),
            partial=False,
            metadata={"expected_edge_bps": expected_edge_bps, "side": getattr(intent, "side", None)},
        )
