from __future__ import annotations

from dataclasses import dataclass

from autonomous_investment_robot.services.policy.strategies.base import Signal


@dataclass
class StrategySignal:
    name: str
    target_notional: float
    confidence: float
    estimated_cost_bps: float
    expected_edge_bps: float
    why: dict


class StrategyPlugin:
    name = "base"

    def compute_signal(self, market_state: dict, features: dict[str, float], regime: str) -> Signal:
        return Signal(0.0, 0.0, 0.0, {"reason": "base"})

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        s = self.compute_signal({}, features, regime)
        return StrategySignal(self.name, s.target_notional, s.confidence, 999.0, s.expected_edge_bps, s.why)


class TrendStrategy(StrategyPlugin):
    name = "trend"

    def compute_signal(self, market_state: dict, features: dict[str, float], regime: str) -> Signal:
        edge = features.get("ret_3", 0.0)
        conf = min(0.99, abs(edge) * 200 + 0.5)
        size = 1200.0 if regime == "TREND" else 300.0
        side_mult = 1.0 if edge >= 0 else -1.0
        return Signal(size * side_mult, conf, abs(edge) * 10000, {"edge": edge, "regime": regime})

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        s = self.compute_signal({}, features, regime)
        return StrategySignal(self.name, s.target_notional, s.confidence, 3.5, s.expected_edge_bps, s.why)


class MeanReversionStrategy(StrategyPlugin):
    name = "mean_reversion"

    def compute_signal(self, market_state: dict, features: dict[str, float], regime: str) -> Signal:
        z = features.get("ret_1", 0.0)
        conf = min(0.95, abs(z) * 180 + 0.45)
        size = 1000.0 if regime == "RANGE" else 200.0
        side_mult = -1.0 if z > 0 else 1.0
        return Signal(size * side_mult, conf, abs(z) * 10000, {"z": z, "regime": regime})

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        s = self.compute_signal({}, features, regime)
        return StrategySignal(self.name, s.target_notional, s.confidence, 3.0, s.expected_edge_bps, s.why)


class CarryStrategy(StrategyPlugin):
    name = "carry"

    def compute_signal(self, market_state: dict, features: dict[str, float], regime: str) -> Signal:
        funding = features.get("funding_rate", 0.0)
        conf = min(0.9, abs(funding) * 10000 + 0.5)
        size = 800.0
        side_mult = -1.0 if funding > 0 else 1.0
        return Signal(size * side_mult, conf, abs(funding) * 10000, {"funding": funding, "regime": regime})

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        s = self.compute_signal({}, features, regime)
        return StrategySignal(self.name, s.target_notional, s.confidence, 2.5, s.expected_edge_bps, s.why)
