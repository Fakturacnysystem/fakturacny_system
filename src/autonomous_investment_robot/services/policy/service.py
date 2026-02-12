from __future__ import annotations

from dataclasses import dataclass

from autonomous_investment_robot.config.settings import PolicySettings
from autonomous_investment_robot.services.models.service import Forecast


@dataclass
class OrderIntent:
    symbol: str
    side: str
    target_notional: float
    why: dict


class PolicyService:
    def __init__(self, settings: PolicySettings) -> None:
        self.settings = settings

    def make_intent(self, fc: Forecast) -> OrderIntent | None:
        edge_bps = abs(fc.mu) * 10000
        if fc.confidence < self.settings.confidence_threshold:
            return None
        if edge_bps <= self.settings.estimated_cost_bps:
            return None

        regime_mult = {"PANIC": 0.25, "TREND": 1.0, "RANGE": 0.6}[fc.regime]
        liq_mult = 0.5 if fc.liquidity_regime == "THIN" else 1.0
        budget = self.settings.base_risk_budget * regime_mult * liq_mult
        notional = min(budget / max(fc.sigma, 1e-6), budget)

        side = "buy" if fc.mu > 0 else "sell"
        return OrderIntent(
            symbol=fc.symbol,
            side=side,
            target_notional=notional,
            why={
                "confidence": fc.confidence,
                "edge_bps": edge_bps,
                "estimated_cost_bps": self.settings.estimated_cost_bps,
                "model_version": fc.model_version,
                "regime": fc.regime,
                "liquidity_regime": fc.liquidity_regime,
                "reason": "edge_above_cost_and_confident",
            },
        )
