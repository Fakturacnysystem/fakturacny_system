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
        notional = min(self.settings.base_risk_budget / max(fc.sigma, 1e-6), self.settings.base_risk_budget)
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
                "reason": "edge_above_cost_and_confident",
            },
        )
