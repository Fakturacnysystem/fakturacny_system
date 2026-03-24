from __future__ import annotations


def estimate_self_impact_bps(
    *,
    target_notional: float,
    depth_notional: float,
    execution_fragility: float,
    execution_style: str = "unchanged",
) -> float:
    if target_notional <= 0.0 or depth_notional <= 0.0:
        return 0.0
    participation = target_notional / max(depth_notional, 1.0)
    style_multiplier = {
        "passive_limit": 0.75,
        "unchanged": 1.0,
        "marketable_limit": 1.15,
        "market": 1.35,
    }.get(execution_style, 1.0)
    return max(0.0, min(30.0, participation * 10000.0 * (0.15 + execution_fragility * 0.35) * style_multiplier))
