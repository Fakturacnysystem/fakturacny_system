from __future__ import annotations

from dataclasses import dataclass

from autonomous_investment_robot.config.settings import AllocatorSettings, PolicySettings, TCOSettings, UNSPECIFIED
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.policy.allocator import BanditAllocator
from autonomous_investment_robot.services.policy.strategy_plugins import CarryStrategy, MeanReversionStrategy, StrategySignal, TrendStrategy
from autonomous_investment_robot.services.policy.tco import edge_from_bps, estimate_cost, should_trade


@dataclass
class OrderIntent:
    symbol: str
    side: str
    target_notional: float
    why: dict


class PolicyService:
    def __init__(self, settings: PolicySettings, allocator_settings: AllocatorSettings, tco_settings: TCOSettings) -> None:
        self.settings = settings
        self.tco_settings = tco_settings
        self.last_veto_reasons: list[str] = []
        self.last_veto_counts: dict[str, int] = {}
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
        self.last_veto_reasons = []
        self.last_veto_counts = {}
        signals = self.evaluate_strategies(features, fc)
        weights = self.allocator.allocate([s.name for s in signals])

        combined = 0.0
        why_parts = []
        for s in signals:
            impact_bps = min(15.0, abs(s.target_notional) / max(features.get("depth_notional", 1.0), 1.0) * 10000)
            cost = estimate_cost(
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
                funding_bps=abs(features.get("funding_rate", 0.0)) * 10000,
                spread_bps=features.get("spread_proxy", 0.0) * 10000,
                impact_bps=impact_bps,
                maker=True,
            )
            edge_info = edge_from_bps(
                strategy_edge_bps=s.expected_edge_bps,
                confidence=s.confidence,
                fc_mu=fc.mu,
                fc_mu_weight=0.1,
            )
            edge = edge_info.estimate
            if self.tco_settings.max_impact_bps != UNSPECIFIED and cost.impact_bps > float(self.tco_settings.max_impact_bps):
                self.last_veto_reasons.append("impact_cap")
                self.last_veto_counts["impact_cap"] = self.last_veto_counts.get("impact_cap", 0) + 1
                continue
            if self.tco_settings.max_total_cost_bps != UNSPECIFIED and cost.total_bps > float(self.tco_settings.max_total_cost_bps):
                self.last_veto_reasons.append("total_cost_cap")
                self.last_veto_counts["total_cost_cap"] = self.last_veto_counts.get("total_cost_cap", 0) + 1
                continue
            if not should_trade(edge, cost, safety_buffer_bps=self.settings.safety_buffer_bps, min_confidence=self.settings.confidence_threshold, confidence=fc.confidence):
                self.last_veto_reasons.append("edge_le_cost")
                self.last_veto_counts["edge_le_cost"] = self.last_veto_counts.get("edge_le_cost", 0) + 1
                continue
            contrib = s.target_notional * weights.get(s.name, 0.0)
            combined += contrib
            why_parts.append(
                {
                    "strategy": s.name,
                    "weight": weights.get(s.name, 0.0),
                    "edge_bps": edge.expected_bps,
                    "strategy_edge_bps_used": edge_info.strategy_edge_bps_used,
                    "fc_mu_used": edge_info.fc_mu_used_bps,
                    "final_edge_bps": edge_info.final_edge_bps,
                    "cost_total_bps": cost.total_bps,
                    "cost_breakdown": {
                        "fees_bps": cost.fees_bps,
                        "slippage_bps": cost.slippage_bps,
                        "funding_bps": cost.funding_bps,
                        "impact_bps": cost.impact_bps,
                        "spread_bps": cost.spread_bps,
                    },
                    **s.why,
                }
            )

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
                "veto_counts": dict(self.last_veto_counts),
                "components": why_parts,
            },
        )

    def update_allocator(self, strategy_pnl_bps: dict[str, float]) -> None:
        for s, pnl in strategy_pnl_bps.items():
            self.allocator.update_performance(s, pnl)
        self.allocator.step_cooldowns()
