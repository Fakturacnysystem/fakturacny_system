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


class DeltaNeutralCarryStrategy(StrategyPlugin):
    name = "delta_neutral_carry"

    def compute_signal(self, market_state: dict, features: dict[str, float], regime: str) -> Signal:
        funding = features.get("funding_rate", 0.0)
        if regime == "PANIC":
            return Signal(0.0, 0.0, 0.0, {"reason": "panic_block"})
        edge_bps = abs(funding) * 10000 * 1.3
        conf = min(0.95, 0.55 + abs(funding) * 15000)
        size = 900.0 if regime in {"RANGE", "TREND"} else 600.0
        side_mult = -1.0 if funding > 0 else 1.0
        return Signal(size * side_mult, conf, edge_bps, {"funding": funding, "market_neutral": True, "regime": regime})

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        s = self.compute_signal({}, features, regime)
        if liq_regime == "THIN":
            s = Signal(s.target_notional * 0.5, max(0.0, s.confidence - 0.1), s.expected_edge_bps * 0.9, {**s.why, "thin_throttle": True})
        return StrategySignal(self.name, s.target_notional, s.confidence, 2.0, s.expected_edge_bps, s.why)


class BasisStrategy(StrategyPlugin):
    name = "basis"

    def compute_signal(self, market_state: dict, features: dict[str, float], regime: str) -> Signal:
        # Optional spot feed proxy; if unavailable, remain inert (stub-ready for record/replay).
        perp = features.get("mark_price", 0.0)
        spot = features.get("spot_price_proxy", 0.0)
        if perp <= 0 or spot <= 0:
            return Signal(0.0, 0.0, 0.0, {"reason": "spot_feed_unavailable_stub"})
        basis = (perp - spot) / max(spot, 1e-9)
        edge_bps = abs(basis) * 10000 * 0.8
        conf = min(0.9, 0.5 + min(0.35, abs(basis) * 50))
        size = 700.0 if regime != "PANIC" else 0.0
        side_mult = -1.0 if basis > 0 else 1.0
        return Signal(size * side_mult, conf, edge_bps, {"basis": basis, "market_neutral": True, "regime": regime})

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        s = self.compute_signal({}, features, regime)
        return StrategySignal(self.name, s.target_notional, s.confidence, 2.2, s.expected_edge_bps, s.why)


class PairsStatArbStrategy(StrategyPlugin):
    name = "pairs_stat_arb"

    def compute_signal(self, market_state: dict, features: dict[str, float], regime: str) -> Signal:
        z = features.get("pairs_zscore", features.get("ret_1", 0.0) * 4.0)
        if regime == "PANIC":
            return Signal(0.0, 0.0, 0.0, {"reason": "panic_block"})
        if regime == "TREND":
            size = 250.0
        else:
            size = 800.0
        side_mult = -1.0 if z > 0 else 1.0
        conf = min(0.92, 0.45 + abs(z) * 0.18)
        edge_bps = min(25.0, abs(z) * 4.0)
        return Signal(size * side_mult, conf, edge_bps, {"pairs_zscore": z, "market_neutral": True, "regime": regime})

    def signal(self, features: dict[str, float], regime: str, liq_regime: str) -> StrategySignal:
        s = self.compute_signal({}, features, regime)
        return StrategySignal(self.name, s.target_notional, s.confidence, 2.4, s.expected_edge_bps, s.why)


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
        if not (regime == "TREND" and liq_regime == "GOOD"):
            s = Signal(s.target_notional * 0.15, max(0.0, s.confidence - 0.15), s.expected_edge_bps * 0.7, {**s.why, "directional_throttled": True})
        else:
            s = Signal(s.target_notional * 0.35, s.confidence, s.expected_edge_bps, {**s.why, "directional_budget": "small"})
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
