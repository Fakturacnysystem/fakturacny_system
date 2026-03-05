from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostEstimate:
    fee_bps: float
    spread_bps: float
    slippage_bps: float
    impact_bps: float
    funding_bps: float
    borrow_bps: float

    @property
    def total_bps(self) -> float:
        return self.fee_bps + self.spread_bps + self.slippage_bps + self.impact_bps + self.funding_bps + self.borrow_bps


class CostEngineService:
    def estimate(
        self,
        *,
        notional: float,
        depth_notional: float,
        spread_bps: float,
        fee_bps: float,
        slippage_bps: float,
        funding_bps: float = 0.0,
        borrow_bps: float = 0.0,
        maker: bool = False,
    ) -> CostEstimate:
        n = max(0.0, float(notional))
        depth = max(1.0, float(depth_notional))
        participation = n / depth
        impact_bps = min(35.0, participation * 10000.0 * 0.35)
        spread_component = max(0.0, float(spread_bps)) * (0.2 if maker else 0.8)
        slip_component = max(0.0, float(slippage_bps)) * (0.55 if maker else 1.1)
        fee_component = max(0.0, float(fee_bps)) * (0.6 if maker else 1.0)
        return CostEstimate(
            fee_bps=fee_component,
            spread_bps=spread_component,
            slippage_bps=slip_component,
            impact_bps=impact_bps,
            funding_bps=max(0.0, float(funding_bps)),
            borrow_bps=max(0.0, float(borrow_bps)),
        )

    def implementation_shortfall_bps(self, *, side: str, arrival_price: float, fill_price: float) -> float:
        arr = max(1e-9, float(arrival_price))
        fill = max(0.0, float(fill_price))
        if side.lower() == "buy":
            return ((fill - arr) / arr) * 10000.0
        return ((arr - fill) / arr) * 10000.0

    def cost_to_alpha_ratio(self, *, alpha_bps: float, cost_bps: float) -> float:
        alpha = abs(float(alpha_bps))
        if alpha <= 1e-9:
            return 999.0 if cost_bps > 0 else 0.0
        return max(0.0, float(cost_bps)) / alpha
