from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StrategySignal:
    name: str
    target_notional: float
    confidence: float
    estimated_cost_bps: float
    why: dict


class StrategyPlugin:
    name = "base"

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        return StrategySignal(self.name, 0.0, 0.0, 999.0, {"reason": "base"})


class TrendStrategy(StrategyPlugin):
    name = "trend"

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        edge = features.get("ret_3", 0.0)
        conf = min(0.99, abs(edge) * 200 + 0.5)
        size = 1200.0 if regime == "TREND" else 300.0
        side_mult = 1.0 if edge >= 0 else -1.0
        return StrategySignal(self.name, size * side_mult, conf, 3.5, {"edge": edge, "regime": regime})


class MeanReversionStrategy(StrategyPlugin):
    name = "mean_reversion"

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        z = features.get("ret_1", 0.0)
        conf = min(0.95, abs(z) * 180 + 0.45)
        size = 1000.0 if regime == "RANGE" else 200.0
        side_mult = -1.0 if z > 0 else 1.0
        return StrategySignal(self.name, size * side_mult, conf, 3.0, {"z": z, "regime": regime})


class CarryStrategy(StrategyPlugin):
    name = "carry"

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        funding = features.get("funding_rate", 0.0)
        conf = min(0.9, abs(funding) * 10000 + 0.5)
        size = 800.0
        # positive funding => prefer short
        side_mult = -1.0 if funding > 0 else 1.0
        return StrategySignal(self.name, size * side_mult, conf, 2.5, {"funding": funding, "regime": regime})
