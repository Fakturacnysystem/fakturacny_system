from __future__ import annotations

from dataclasses import dataclass

from autonomous_investment_robot.config.settings import AllocatorSettings, PolicySettings
from autonomous_investment_robot.services.execution.tco import edge_after_cost, estimate_total_cost_bps
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.policy.allocator import BanditAllocator
from autonomous_investment_robot.services.policy.strategy_plugins import CarryStrategy, MeanReversionStrategy, StrategySignal, TrendStrategy


@dataclass
class OrderIntent:
    symbol: str
    side: str
    target_notional: float
    why: dict


class PolicyService:
    def __init__(self, settings: PolicySettings, allocator_settings: AllocatorSettings) -> None:
        self.settings = settings
        self.allocator = BanditAllocator(
            decay=allocator_settings.decay,
            max_weight=allocator_settings.max_weight_per_strategy,
            min_samples=allocator_settings.min_samples,
            fatal_sigma_loss=allocator_settings.fatal_sigma_loss,
            cooldown_steps=allocator_settings.cooldown_steps,
        )
        self.strategies = [TrendStrategy(), MeanReversionStrategy(), CarryStrategy()]

    def evaluate_strategies(self, features: dict[str, float], forecast: Forecast) -> list[StrategySignal]:
        return [s.signal(features, forecast.regime, forecast.liquidity_regime) for s in self.strategies]

    def make_intent(self, fc: Forecast, features: dict[str, float], fee_bps: float, slippage_bps: float) -> OrderIntent | None:
        signals = self.evaluate_strategies(features, fc)
        weights = self.allocator.allocate([s.name for s in signals])

        combined = 0.0
        why_parts = []
        for s in signals:
            total_cost = estimate_total_cost_bps(
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                funding_bps=abs(features.get("funding_rate", 0.0)) * 10000,
                spread_bps=features.get("spread_proxy", 0.0) * 10000,
                maker=True,
            )
            edge_bps = abs(fc.mu) * 10000 * s.confidence
            net_edge = edge_after_cost(edge_bps, total_cost)
            if net_edge <= 0:
                continue
            contrib = s.target_notional * weights.get(s.name, 0.0)
            combined += contrib
            why_parts.append({"strategy": s.name, "weight": weights.get(s.name, 0.0), "net_edge_bps": net_edge, **s.why})

        if abs(combined) < 1e-9 or fc.confidence < self.settings.confidence_threshold:
            return None

        side = "buy" if combined > 0 else "sell"
        target = min(abs(combined), self.settings.base_risk_budget)
        return OrderIntent(
            symbol=fc.symbol,
            side=side,
            target_notional=target,
            why={
                "confidence": fc.confidence,
                "regime": fc.regime,
                "liquidity_regime": fc.liquidity_regime,
                "weights": weights,
                "components": why_parts,
            },
        )

    def update_allocator(self, strategy_pnl_bps: dict[str, float]) -> None:
        for s, pnl in strategy_pnl_bps.items():
            self.allocator.update_performance(s, pnl)
        self.allocator.step_cooldowns()
