from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostBreakdown:
    fees_bps: float
    slippage_bps: float
    funding_bps: float
    impact_bps: float
    spread_bps: float
    total_bps: float


@dataclass
class EdgeEstimate:
    expected_bps: float
    uncertainty: float


def estimate_cost(*, fee_bps: float, slippage_bps: float, funding_bps: float, spread_bps: float, impact_bps: float, maker: bool) -> CostBreakdown:
    maker_fee = fee_bps * (0.6 if maker else 1.0)
    total = maker_fee + slippage_bps + funding_bps + impact_bps + spread_bps * 0.2
    return CostBreakdown(
        fees_bps=maker_fee,
        slippage_bps=slippage_bps,
        funding_bps=funding_bps,
        impact_bps=impact_bps,
        spread_bps=spread_bps,
        total_bps=total,
    )


def estimate_edge(*, forecast_mu: float, confidence: float, horizon_scale: float = 1.0) -> EdgeEstimate:
    expected = abs(forecast_mu) * 10000 * confidence * horizon_scale
    uncertainty = max(0.0, (1.0 - confidence) * expected)
    return EdgeEstimate(expected_bps=expected, uncertainty=uncertainty)


def should_trade(edge: EdgeEstimate, cost: CostBreakdown, safety_buffer_bps: float, min_confidence: float, confidence: float) -> bool:
    if confidence < min_confidence:
        return False
    return edge.expected_bps > (cost.total_bps + safety_buffer_bps)
