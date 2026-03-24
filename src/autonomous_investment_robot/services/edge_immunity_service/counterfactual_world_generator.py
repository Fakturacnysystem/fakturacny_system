from __future__ import annotations

from datetime import datetime

from autonomous_investment_robot.core.contracts import CounterfactualWorld


def generate_worlds(*, ts: datetime, spread_bps: float, depth_notional: float, execution_fragility: float, regime_label: str) -> list[CounterfactualWorld]:
    thinness = max(0.0, min(1.0, 1.0 - min(depth_notional / 250000.0, 1.0)))
    return [
        CounterfactualWorld("spread_widening", 0.19, 1.8, 0.9, 0.0, 1.1, 1.1, 0.0, "spread_shock", 0.85, 0.0, "passive_limit", {"ts": ts.isoformat()}),
        CounterfactualWorld("thin_book", 0.17 + thinness * 0.12, 1.4, 0.55, 0.0, 1.15, 1.3, 0.0, "liquidity_thin", 0.72, 0.0, "passive_limit", {}),
        CounterfactualWorld("adverse_move", 0.16 + execution_fragility * 0.1, 1.1, 0.8, -max(4.0, spread_bps), 1.25, 1.05, 0.0, "adverse_selection", 0.8, 3.0, "marketable_limit", {}),
        CounterfactualWorld("slower_fill", 0.12 + execution_fragility * 0.08, 1.15, 0.75, -max(2.0, spread_bps * 0.4), 1.0, 1.15, 0.0, "slow_fill", 0.65, 9.0, "passive_limit", {}),
        CounterfactualWorld("liquidity_sweep", 0.14 if regime_label != "dead_market" else 0.08, 1.5, 0.6, -max(6.0, spread_bps * 1.2), 1.2, 1.25, 0.0, "liquidity_sweep", 0.7, 4.0, "marketable_limit", {}),
        CounterfactualWorld("wait_improves_entry", 0.10, 0.8, 1.1, 0.0, 0.95, 0.8, max(1.0, spread_bps * 0.5), "wait_dominance", 1.05, 12.0, "passive_limit", {}),
    ]
