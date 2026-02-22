from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from autonomous_investment_robot.config.settings import AllocatorSettings, PolicySettings, TCOSettings, UNSPECIFIED
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.policy.allocator import BanditAllocator
from autonomous_investment_robot.services.policy.strategy_plugins import (
    BasisStrategy,
    CarryStrategy,
    DeltaNeutralCarryStrategy,
    MeanReversionStrategy,
    PairsStatArbStrategy,
    StrategySignal,
    TrendStrategy,
)
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
        self.strategy_regime_cooldowns: dict[tuple[str, str], int] = {}
        self.strategy_regime_veto_streaks: dict[tuple[str, str], int] = defaultdict(int)
        self.allocator = BanditAllocator(
            decay=allocator_settings.decay,
            max_weight=allocator_settings.max_weight_per_strategy,
            min_samples=allocator_settings.min_samples,
            fatal_sigma_loss=allocator_settings.fatal_sigma_loss,
            cooldown_steps=allocator_settings.cooldown_steps,
        )
        self.strategies = [
            DeltaNeutralCarryStrategy(),
            BasisStrategy(),
            PairsStatArbStrategy(),
            CarryStrategy(),
            MeanReversionStrategy(),
            TrendStrategy(),
        ]

    def evaluate_strategies(self, features: dict[str, float], forecast: Forecast) -> list[StrategySignal]:
        out: list[StrategySignal] = []
        for s in self.strategies:
            key = (s.name, forecast.regime)
            cd = self.strategy_regime_cooldowns.get(key, 0)
            if cd > 0:
                self.strategy_regime_cooldowns[key] = cd - 1
                continue
            out.append(s.signal(features, forecast.regime, forecast.liquidity_regime))
        return out

    def _regime_priority_multiplier(self, strategy_name: str, regime: str, liq_regime: str) -> float:
        market_neutral = strategy_name in {"delta_neutral_carry", "basis", "pairs_stat_arb", "carry"}
        if market_neutral:
            if regime == "PANIC":
                return 0.3
            if liq_regime == "THIN":
                return 0.6
            return 1.25
        if strategy_name == "trend":
            return 1.0 if (regime == "TREND" and liq_regime == "GOOD") else 0.2
        if strategy_name == "mean_reversion":
            return 1.1 if regime == "RANGE" else 0.5
        return 1.0

    def _record_regime_veto(self, strategy_name: str, regime: str) -> None:
        key = (strategy_name, regime)
        self.strategy_regime_veto_streaks[key] += 1
        if self.strategy_regime_veto_streaks[key] >= 3:
            self.strategy_regime_cooldowns[key] = max(self.strategy_regime_cooldowns.get(key, 0), 5)
            self.strategy_regime_veto_streaks[key] = 0

    def _clear_regime_veto_streak(self, strategy_name: str, regime: str) -> None:
        self.strategy_regime_veto_streaks[(strategy_name, regime)] = 0

    def make_intent(self, fc: Forecast, features: dict[str, float], fee_bps: float, slippage_bps: float) -> OrderIntent | None:
        self.last_veto_reasons = []
        self.last_veto_counts = {}
        signals = self.evaluate_strategies(features, fc)
        if not signals:
            return None
        weights = self.allocator.allocate([s.name for s in signals])

        combined = 0.0
        why_parts = []
        net_scores: dict[str, float] = {}
        accepted_candidates: list[tuple[StrategySignal, float, object, object]] = []
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
                self._record_regime_veto(s.name, fc.regime)
                continue
            if self.tco_settings.max_total_cost_bps != UNSPECIFIED and cost.total_bps > float(self.tco_settings.max_total_cost_bps):
                self.last_veto_reasons.append("total_cost_cap")
                self.last_veto_counts["total_cost_cap"] = self.last_veto_counts.get("total_cost_cap", 0) + 1
                self._record_regime_veto(s.name, fc.regime)
                continue
            if not should_trade(edge, cost, safety_buffer_bps=self.settings.safety_buffer_bps, min_confidence=self.settings.confidence_threshold, confidence=fc.confidence):
                self.last_veto_reasons.append("edge_le_cost")
                self.last_veto_counts["edge_le_cost"] = self.last_veto_counts.get("edge_le_cost", 0) + 1
                self._record_regime_veto(s.name, fc.regime)
                continue
            self._clear_regime_veto_streak(s.name, fc.regime)
            net_after_cost_bps = edge.expected_bps - cost.total_bps
            regime_mult = self._regime_priority_multiplier(s.name, fc.regime, fc.liquidity_regime)
            net_scores[s.name] = max(0.0, net_after_cost_bps) * regime_mult
            accepted_candidates.append((s, impact_bps, cost, edge_info))
            why_parts.append(
                {
                    "strategy": s.name,
                    "weight": weights.get(s.name, 0.0),
                    "edge_bps": edge.expected_bps,
                    "strategy_edge_bps_used": edge_info.strategy_edge_bps_used,
                    "fc_mu_used": edge_info.fc_mu_used_bps,
                    "final_edge_bps": edge_info.final_edge_bps,
                    "net_after_cost_bps": net_after_cost_bps,
                    "regime_priority_mult": regime_mult,
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

        if accepted_candidates:
            total_net = sum(net_scores.values())
            effective_weights: dict[str, float] = {}
            if total_net > 0:
                effective_weights = {name: v / total_net for name, v in net_scores.items()}
            else:
                effective_weights = {s.name: weights.get(s.name, 0.0) for s, *_ in accepted_candidates}
            for comp in why_parts:
                comp["allocator_weight_raw"] = comp["weight"]
                comp["weight"] = effective_weights.get(comp["strategy"], 0.0)
            for s, _impact_bps, _cost, _edge_info in accepted_candidates:
                contrib = s.target_notional * effective_weights.get(s.name, 0.0)
                combined += contrib

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
                "weights_net_after_costs": {k: v for k, v in sorted({c["strategy"]: c["weight"] for c in why_parts}.items())},
                "veto_counts": dict(self.last_veto_counts),
                "strategy_regime_cooldowns": {f"{k[0]}@{k[1]}": v for k, v in sorted(self.strategy_regime_cooldowns.items()) if v > 0},
                "components": why_parts,
            },
        )

    def update_allocator(self, strategy_pnl_bps: dict[str, float]) -> None:
        for s, pnl in strategy_pnl_bps.items():
            self.allocator.update_performance(s, pnl)
        self.allocator.step_cooldowns()
