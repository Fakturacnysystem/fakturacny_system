from __future__ import annotations


def estimate_total_cost_bps(fee_bps: float, slippage_bps: float, funding_bps: float, spread_bps: float, maker: bool) -> float:
    maker_discount = 0.6 if maker else 1.0
    return fee_bps * maker_discount + slippage_bps + funding_bps + spread_bps * 0.2


def edge_after_cost(edge_bps: float, total_cost_bps: float) -> float:
    return edge_bps - total_cost_bps


def slice_notional(target_notional: float, slicing_parts: int, max_participation_rate: float, depth_notional: float) -> list[float]:
    cap = depth_notional * max_participation_rate
    bounded = min(abs(target_notional), cap)
    part = bounded / max(1, slicing_parts)
    return [part for _ in range(max(1, slicing_parts))]


def anti_toxic_block(oi_spike_pct: float, liquidations: float, funding_rate: float, spread_bps: float) -> bool:
    return oi_spike_pct > 2.0 and liquidations > 100000 and abs(funding_rate) > 0.0004 and spread_bps > 20
