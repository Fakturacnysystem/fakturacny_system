from __future__ import annotations

from typing import Any


def pair_score(
    *,
    spread_bps: float,
    depth_notional: float,
    realized_volatility: float,
    signal_stability: float,
    fill_quality: float,
    execution_friction: float,
    expectancy_bps: float,
    reject_burden: float,
    capital_capacity: float,
    regime_compatibility: float,
    capital_efficiency: float,
    microstructure_quality: float,
    crowding_penalty: float,
) -> float:
    score = (
        max(0.0, 1.0 - min(spread_bps / 40.0, 1.0)) * 0.10
        + max(0.0, min(depth_notional / 50000.0, 1.0)) * 0.10
        + max(0.0, min(realized_volatility / 0.02, 1.0)) * 0.05
        + max(0.0, min(signal_stability, 1.0)) * 0.10
        + max(0.0, min(fill_quality, 1.0)) * 0.10
        + max(0.0, 1.0 - min(execution_friction, 1.0)) * 0.10
        + max(0.0, min(expectancy_bps / 30.0, 1.0)) * 0.10
        + max(0.0, 1.0 - min(reject_burden, 1.0)) * 0.05
        + max(0.0, min(capital_capacity, 1.0)) * 0.05
        + max(0.0, min(regime_compatibility, 1.0)) * 0.10
        + max(0.0, min(capital_efficiency, 1.0)) * 0.10
        + max(0.0, min(microstructure_quality, 1.0)) * 0.10
        - max(0.0, min(crowding_penalty, 1.0)) * 0.05
    )
    return max(0.0, min(1.0, score))


def eligibility_reasons(*, spread_bps: float, depth_notional: float, expectancy_bps: float, fill_rate: float, settings: Any) -> list[str]:
    reasons: list[str] = []
    if spread_bps > float(settings.market_universe.pair_max_spread_bps):
        reasons.append("spread_above_pair_max")
    if depth_notional < float(settings.market_universe.pair_min_depth_notional):
        reasons.append("depth_below_pair_min")
    if expectancy_bps < float(settings.market_universe.pair_min_expectancy_bps):
        reasons.append("expectancy_below_pair_min")
    if fill_rate < float(settings.market_universe.pair_min_fill_rate):
        reasons.append("fill_rate_below_pair_min")
    return reasons

