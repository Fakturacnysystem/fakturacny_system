from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timezone
from types import SimpleNamespace

from autonomous_investment_robot.config.settings import AllocatorSettings, PolicySettings, TCOSettings, UNSPECIFIED
from autonomous_investment_robot.core.contracts import EdgeImmunityDecision, ExecutionQualityForecast, NoTradeDecision, PolicyDecision, PortfolioAllocation, QuantumState, RegimeAssessment
from autonomous_investment_robot.services.models.service import Forecast
from autonomous_investment_robot.services.decision_doctrine_service.service import DecisionDoctrineService
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
from autonomous_investment_robot.services.shadow_rival_service.service import ShadowRivalService
from autonomous_investment_robot.services.spre_service.service import SPREEngine


@dataclass
class OrderIntent:
    symbol: str
    side: str
    target_notional: float
    why: dict


class PolicyService:
    def __init__(
        self,
        settings: PolicySettings,
        allocator_settings: AllocatorSettings,
        tco_settings: TCOSettings,
        *,
        spre_engine: object | None = None,
        shadow_rival_service: object | None = None,
        decision_doctrine_service: object | None = None,
        long_only: bool = False,
    ) -> None:
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
        self.spre_engine = SPREEngine() if spre_engine is None else spre_engine
        self.shadow_rival_service = ShadowRivalService() if shadow_rival_service is None else shadow_rival_service
        self.decision_doctrine_service = DecisionDoctrineService() if decision_doctrine_service is None else decision_doctrine_service
        self.long_only = bool(long_only)

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

    def evaluate_decision(
        self,
        fc: Forecast,
        features: dict[str, float],
        fee_bps: float,
        slippage_bps: float,
        *,
        regime_assessment: RegimeAssessment | None = None,
        execution_quality: ExecutionQualityForecast | None = None,
        portfolio_allocation: PortfolioAllocation | None = None,
        quantum_state: QuantumState | None = None,
        edge_immunity_decision: EdgeImmunityDecision | None = None,
        profitability_context: dict | None = None,
        inventory_context: dict | None = None,
        event_intelligence_report: object | None = None,
        synthetic_affect_state: object | None = None,
        capital_sovereignty_decision: object | None = None,
        position_morph_plan: object | None = None,
        adaptive_exit_allocation: object | None = None,
        execution_simulation_report: object | None = None,
        human_escalation_decision: object | None = None,
        truth_context: dict | None = None,
        market_integrity_status: object | None = None,
        provider_capability: object | None = None,
        mastermind_advisory: object | None = None,
        market_watch_report: object | None = None,
    ) -> PolicyDecision:
        self.last_veto_reasons = []
        self.last_veto_counts = {}
        signals = self.evaluate_strategies(features, fc)
        if not signals:
            return PolicyDecision(
                symbol=fc.symbol,
                ts=fc.ts,
                trade_allowed=False,
                no_trade=NoTradeDecision(symbol=fc.symbol, ts=fc.ts, reason="no_signals", reasons=["no_signals"]),
            )
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

        weighted_confidence = max([fc.confidence, *(c[0].confidence for c in accepted_candidates)] if accepted_candidates else [fc.confidence])
        expected_cost_bps = 0.0 if not why_parts else sum(float(c["cost_total_bps"]) * float(c["weight"]) for c in why_parts)
        expected_edge_bps = 0.0 if not why_parts else sum(float(c["final_edge_bps"]) * float(c["weight"]) for c in why_parts)
        uncertainty = max(0.0, min(1.0, 1.0 - weighted_confidence))
        regime_fit = 1.0 if regime_assessment is None else max(0.0, min(1.0, regime_assessment.confidence * regime_assessment.persistence))
        capacity_limit = max(float(features.get("depth_notional", 0.0)) * 0.1, self.settings.base_risk_budget)
        size_multiplier = 1.0

        no_trade_reason = None
        reasons: list[str] = []
        if fc.confidence < self.settings.confidence_threshold:
            no_trade_reason = "confidence_guard"
            reasons.append("confidence_guard")
        if execution_quality is not None and execution_quality.fill_probability < 0.2:
            no_trade_reason = no_trade_reason or "execution_quality_bad"
            reasons.append("execution_quality_bad")
        if float(features.get("depth_notional", 0.0)) <= 0.0:
            no_trade_reason = no_trade_reason or "liquidity_too_thin"
            reasons.append("liquidity_too_thin")
        if regime_assessment is not None and regime_assessment.label in {"dead_market", "liquidity_vacuum", "news_chaos"}:
            no_trade_reason = no_trade_reason or "regime_unfavorable"
            reasons.append("regime_unfavorable")
        if self.last_veto_reasons and not accepted_candidates:
            no_trade_reason = no_trade_reason or "no_edge_after_costs"
            reasons.extend(sorted(set(self.last_veto_reasons)))
        if abs(combined) < 1e-9:
            no_trade_reason = no_trade_reason or "no_edge_after_costs"
            reasons.append("zero_combined_signal")

        why = {
            "confidence": fc.confidence,
            "regime": fc.regime,
            "liquidity_regime": fc.liquidity_regime,
            "weights": weights,
            "weights_net_after_costs": {k: v for k, v in sorted({c["strategy"]: c["weight"] for c in why_parts}.items())},
            "veto_counts": dict(self.last_veto_counts),
            "strategy_regime_cooldowns": {f"{k[0]}@{k[1]}": v for k, v in sorted(self.strategy_regime_cooldowns.items()) if v > 0},
            "components": why_parts,
        }
        if regime_assessment is not None:
            why["regime_assessment"] = {
                "label": regime_assessment.label,
                "confidence": regime_assessment.confidence,
                "persistence": regime_assessment.persistence,
                "transition_probability": regime_assessment.transition_probability,
                "degradation_warning": regime_assessment.degradation_warning,
            }
        if execution_quality is not None:
            why["execution_quality"] = {
                "fill_probability": execution_quality.fill_probability,
                "expected_fill_speed_ms": execution_quality.expected_fill_speed_ms,
                "expected_price_quality_bps": execution_quality.expected_price_quality_bps,
                "adverse_selection_risk": execution_quality.adverse_selection_risk,
                "passive_preferred": execution_quality.passive_preferred,
            }
        if portfolio_allocation is not None:
            why["portfolio_allocation"] = {
                "recommended_notional": portfolio_allocation.recommended_notional,
                "concentration_score": portfolio_allocation.concentration_score,
                "opportunity_cost_score": portfolio_allocation.opportunity_cost_score,
                "volatility_scalar": portfolio_allocation.volatility_scalar,
                "liquidity_scalar": portfolio_allocation.liquidity_scalar,
                "drawdown_scalar": portfolio_allocation.drawdown_scalar,
                "regime_scalar": portfolio_allocation.regime_scalar,
                "confidence_scalar": portfolio_allocation.confidence_scalar,
                "uncertainty_scalar": portfolio_allocation.uncertainty_scalar,
            }
        if truth_context is not None:
            snapshot = truth_context.get("snapshot", truth_context.get("truth_confidence", truth_context))
            why["truth_context"] = {
                "snapshot": snapshot if isinstance(snapshot, dict) else {},
                "reconciliation_ok": bool(truth_context.get("reconciliation_ok", True)),
            }
        if market_integrity_status is not None:
            why["market_integrity"] = {
                "score": float(getattr(market_integrity_status, "score", 0.0) or 0.0),
                "action": str(getattr(market_integrity_status, "action", "continue") or "continue"),
                "confidence": str(getattr(market_integrity_status, "confidence", "unknown") or "unknown"),
                "reasons": list(getattr(market_integrity_status, "reasons", []) or []),
            }
        if provider_capability is not None:
            why["provider_capability"] = {
                "lifecycle_completeness": str(getattr(provider_capability, "lifecycle_completeness", "")),
                "user_stream_confidence": str(getattr(provider_capability, "user_stream_confidence", "")),
                "fee_truth_confidence": str(getattr(provider_capability, "fee_truth_confidence", "")),
                "replace_supported": bool(getattr(provider_capability, "replace_supported", False)),
                "expire_supported": bool(getattr(provider_capability, "expire_supported", False)),
            }
        if market_watch_report is not None:
            why["market_watch"] = {
                "action": str(getattr(market_watch_report, "action", "continue") or "continue"),
                "score": float(getattr(market_watch_report, "score", 1.0) or 1.0),
                "blackout_active": bool(getattr(market_watch_report, "blackout_active", False)),
                "liquidity_score": float(getattr(market_watch_report, "liquidity_score", 1.0) or 1.0),
                "spread_score": float(getattr(market_watch_report, "spread_score", 1.0) or 1.0),
                "reasons": list(getattr(market_watch_report, "reasons", []) or []),
                "metadata": dict(getattr(market_watch_report, "metadata", {}) or {}),
            }
            market_watch_action = str(getattr(market_watch_report, "action", "continue") or "continue")
            if market_watch_action == "block_entries":
                no_trade_reason = no_trade_reason or "market_watch_block_entries"
                reasons.append("market_watch_block_entries")
            elif market_watch_action == "degrade":
                size_multiplier = min(size_multiplier, 0.5)
                reasons.append("market_watch_degrade")
        if mastermind_advisory is not None:
            why["mastermind"] = {
                "provider": str(getattr(mastermind_advisory, "provider", "")),
                "signal": str(getattr(mastermind_advisory, "signal", "")),
                "confidence": float(getattr(mastermind_advisory, "confidence", 0.0) or 0.0),
                "reason": str(getattr(mastermind_advisory, "reason", "")),
                "decision": str(getattr(mastermind_advisory, "decision", "CONTINUE") or "CONTINUE"),
                "risk_level": float(getattr(mastermind_advisory, "risk_level", 0.0) or 0.0),
                "veto": bool(getattr(mastermind_advisory, "veto", False)),
                "size_multiplier": float(getattr(mastermind_advisory, "size_multiplier", 1.0) or 1.0),
                "execution_style_bias": str(getattr(mastermind_advisory, "execution_style_bias", "unchanged") or "unchanged"),
                "reasons": list(getattr(mastermind_advisory, "reasons", []) or []),
                "heuristic": bool(getattr(mastermind_advisory, "heuristic", True)),
                "raw": dict(getattr(mastermind_advisory, "raw", {}) or {}),
            }
            mastermind_action = str(getattr(mastermind_advisory, "decision", "CONTINUE") or "CONTINUE").lower()
            mastermind_confidence = float(getattr(mastermind_advisory, "confidence", 0.0) or 0.0)
            size_multiplier = min(size_multiplier, float(getattr(mastermind_advisory, "size_multiplier", 1.0) or 1.0))
            if bool(getattr(mastermind_advisory, "veto", False)) or (mastermind_action in {"no_trade", "hold"} and mastermind_confidence >= 0.45):
                no_trade_reason = no_trade_reason or "mastermind_veto"
                reasons.append("mastermind_veto")
            elif mastermind_action == "wait" and mastermind_confidence >= 0.40:
                no_trade_reason = no_trade_reason or "mastermind_wait"
                reasons.append("mastermind_wait")
            elif mastermind_action == "probe":
                size_multiplier = min(size_multiplier, 0.25)
                reasons.append("mastermind_probe")
            elif mastermind_action == "trade_smaller":
                size_multiplier = min(size_multiplier, 0.5)
                reasons.append("mastermind_trade_smaller")
        if event_intelligence_report is not None:
            why["event_intelligence"] = {
                "recommended_action": getattr(event_intelligence_report, "recommended_action", "continue"),
                "overall_risk_score": float(getattr(event_intelligence_report, "overall_risk_score", 0.0) or 0.0),
                "recommended_size_multiplier": float(getattr(event_intelligence_report, "recommended_size_multiplier", 1.0) or 1.0),
                "reasons": list(getattr(event_intelligence_report, "reasons", []) or []),
                "partial": bool(getattr(event_intelligence_report, "partial", False)),
                "heuristic": bool(getattr(event_intelligence_report, "metadata", {}).get("heuristic", True)),
            }
            event_action = str(getattr(event_intelligence_report, "recommended_action", "continue"))
            size_multiplier = min(size_multiplier, float(getattr(event_intelligence_report, "recommended_size_multiplier", 1.0) or 1.0))
            if event_action == "no_trade":
                no_trade_reason = no_trade_reason or "event_intelligence_no_trade"
                reasons.append("event_intelligence_no_trade")
            elif event_action == "wait":
                no_trade_reason = no_trade_reason or "event_intelligence_wait"
                reasons.append("event_intelligence_wait")
            elif event_action == "trade_smaller":
                reasons.append("event_intelligence_trade_smaller")
        if synthetic_affect_state is not None:
            why["synthetic_affect"] = {
                "confidence_state": float(getattr(synthetic_affect_state, "confidence_state", 0.0) or 0.0),
                "caution": float(getattr(synthetic_affect_state, "caution", 0.0) or 0.0),
                "stress": float(getattr(synthetic_affect_state, "stress", 0.0) or 0.0),
                "conviction": float(getattr(synthetic_affect_state, "conviction", 0.0) or 0.0),
                "fear": float(getattr(synthetic_affect_state, "fear", 0.0) or 0.0),
                "asymmetry": float(getattr(synthetic_affect_state, "asymmetry", 0.0) or 0.0),
                "aggression_clamp": float(getattr(synthetic_affect_state, "aggression_clamp", 1.0) or 1.0),
                "no_trade_threshold_shift": float(getattr(synthetic_affect_state, "no_trade_threshold_shift", 0.0) or 0.0),
                "recommended_action": str(getattr(synthetic_affect_state, "recommended_action", "continue")),
                "reasons": list(getattr(synthetic_affect_state, "reasons", []) or []),
                "partial": bool(getattr(synthetic_affect_state, "partial", False)),
            }
            size_multiplier = min(size_multiplier, float(getattr(synthetic_affect_state, "aggression_clamp", 1.0) or 1.0))
            uncertainty = max(
                uncertainty,
                min(
                    1.0,
                    uncertainty + float(getattr(synthetic_affect_state, "no_trade_threshold_shift", 0.0) or 0.0),
                ),
            )
            affect_action = str(getattr(synthetic_affect_state, "recommended_action", "continue"))
            if affect_action == "no_trade":
                no_trade_reason = no_trade_reason or "synthetic_affect_no_trade"
                reasons.append("synthetic_affect_no_trade")
            elif affect_action == "trade_smaller":
                reasons.append("synthetic_affect_trade_smaller")
        if capital_sovereignty_decision is not None:
            why["capital_sovereignty"] = {
                "action": str(getattr(capital_sovereignty_decision, "action", "continue")),
                "freedom_envelope_score": float(getattr(capital_sovereignty_decision, "freedom_envelope_score", 0.0) or 0.0),
                "reserve_pressure": float(getattr(capital_sovereignty_decision, "reserve_pressure", 0.0) or 0.0),
                "rotation_score": float(getattr(capital_sovereignty_decision, "rotation_score", 0.0) or 0.0),
                "recommended_size_multiplier": float(getattr(capital_sovereignty_decision, "recommended_size_multiplier", 1.0) or 1.0),
                "keep_core_ratio": float(getattr(capital_sovereignty_decision, "keep_core_ratio", 0.0) or 0.0),
                "satellite_ratio": float(getattr(capital_sovereignty_decision, "satellite_ratio", 0.0) or 0.0),
                "probe_ratio": float(getattr(capital_sovereignty_decision, "probe_ratio", 0.0) or 0.0),
                "release_notional": float(getattr(capital_sovereignty_decision, "release_notional", 0.0) or 0.0),
                "rotate_notional": float(getattr(capital_sovereignty_decision, "rotate_notional", 0.0) or 0.0),
                "reasons": list(getattr(capital_sovereignty_decision, "reasons", []) or []),
                "partial": bool(getattr(capital_sovereignty_decision, "partial", False)),
            }
            sovereignty_action = str(getattr(capital_sovereignty_decision, "action", "continue"))
            size_multiplier = min(size_multiplier, float(getattr(capital_sovereignty_decision, "recommended_size_multiplier", 1.0) or 1.0))
            if sovereignty_action == "no_trade":
                no_trade_reason = no_trade_reason or "capital_sovereignty_no_trade"
                reasons.append("capital_sovereignty_no_trade")
            elif sovereignty_action == "wait":
                no_trade_reason = no_trade_reason or "capital_sovereignty_wait"
                reasons.append("capital_sovereignty_wait")
            elif sovereignty_action == "probe_only":
                probe_ratio = float(getattr(capital_sovereignty_decision, "probe_ratio", 0.0) or 0.0)
                size_multiplier = min(size_multiplier, probe_ratio if probe_ratio > 0.0 else 0.3)
                reasons.append("capital_sovereignty_probe_only")
            elif sovereignty_action == "trade_smaller":
                reasons.append("capital_sovereignty_trade_smaller")
            elif sovereignty_action == "release":
                no_trade_reason = no_trade_reason or "capital_release_priority"
                reasons.append("capital_release_priority")
            elif sovereignty_action == "rotate":
                no_trade_reason = no_trade_reason or "capital_rotation_priority"
                reasons.append("capital_rotation_priority")
        if position_morph_plan is not None:
            why["position_morph"] = {
                "action": str(getattr(position_morph_plan, "action", "continue")),
                "keep_core": bool(getattr(position_morph_plan, "keep_core", False)),
                "trim_satellites": bool(getattr(position_morph_plan, "trim_satellites", False)),
                "allow_runner": bool(getattr(position_morph_plan, "allow_runner", False)),
                "reduce_risk": bool(getattr(position_morph_plan, "reduce_risk", False)),
                "core_fraction": float(getattr(position_morph_plan, "core_fraction", 0.0) or 0.0),
                "satellite_fraction": float(getattr(position_morph_plan, "satellite_fraction", 0.0) or 0.0),
                "runner_fraction": float(getattr(position_morph_plan, "runner_fraction", 0.0) or 0.0),
                "add_notional": float(getattr(position_morph_plan, "add_notional", 0.0) or 0.0),
                "reduce_notional": float(getattr(position_morph_plan, "reduce_notional", 0.0) or 0.0),
                "probe_notional": float(getattr(position_morph_plan, "probe_notional", 0.0) or 0.0),
                "reasons": list(getattr(position_morph_plan, "reasons", []) or []),
                "partial": bool(getattr(position_morph_plan, "partial", False)),
            }
            if bool(getattr(position_morph_plan, "reduce_risk", False)):
                reasons.append("position_morph_reduce")
                size_multiplier = min(size_multiplier, 0.75)
            if float(getattr(position_morph_plan, "probe_notional", 0.0) or 0.0) > 0.0:
                reasons.append("position_morph_probe")
        if adaptive_exit_allocation is not None:
            why["adaptive_exit"] = {
                "action": str(getattr(adaptive_exit_allocation, "action", "hold")),
                "core_exit_notional": float(getattr(adaptive_exit_allocation, "core_exit_notional", 0.0) or 0.0),
                "satellite_exit_notional": float(getattr(adaptive_exit_allocation, "satellite_exit_notional", 0.0) or 0.0),
                "runner_notional": float(getattr(adaptive_exit_allocation, "runner_notional", 0.0) or 0.0),
                "total_exit_notional": float(getattr(adaptive_exit_allocation, "total_exit_notional", 0.0) or 0.0),
                "execution_style": str(getattr(adaptive_exit_allocation, "execution_style", "passive_limit")),
                "reasons": list(getattr(adaptive_exit_allocation, "reasons", []) or []),
                "partial": bool(getattr(adaptive_exit_allocation, "partial", False)),
            }
            adaptive_action = str(getattr(adaptive_exit_allocation, "action", "hold"))
            total_exit_notional = float(getattr(adaptive_exit_allocation, "total_exit_notional", 0.0) or 0.0)
            if adaptive_action in {"partial_exit", "risk_exit", "flatten"} and total_exit_notional > 0.0:
                no_trade_reason = no_trade_reason or "adaptive_exit_priority"
                reasons.append("adaptive_exit_priority")
        if execution_simulation_report is not None:
            why["execution_simulation"] = {
                "recommended_action": str(getattr(execution_simulation_report, "recommended_action", "continue")),
                "recommended_execution_style": str(getattr(execution_simulation_report, "recommended_execution_style", "passive_limit")),
                "expected_fill_probability": float(getattr(execution_simulation_report, "expected_fill_probability", 0.0) or 0.0),
                "stressed_fill_probability": float(getattr(execution_simulation_report, "stressed_fill_probability", 0.0) or 0.0),
                "expected_slippage_bps": float(getattr(execution_simulation_report, "expected_slippage_bps", 0.0) or 0.0),
                "worst_case_cost_bps": float(getattr(execution_simulation_report, "worst_case_cost_bps", 0.0) or 0.0),
                "reasons": list(getattr(execution_simulation_report, "reasons", []) or []),
                "partial": bool(getattr(execution_simulation_report, "partial", False)),
            }
            sim_action = str(getattr(execution_simulation_report, "recommended_action", "continue"))
            if sim_action == "no_trade":
                no_trade_reason = no_trade_reason or "execution_simulation_no_trade"
                reasons.append("execution_simulation_no_trade")
            elif sim_action == "wait":
                no_trade_reason = no_trade_reason or "execution_simulation_wait"
                reasons.append("execution_simulation_wait")
            elif sim_action == "trade_smaller":
                size_multiplier = min(size_multiplier, 0.5)
                reasons.append("execution_simulation_trade_smaller")
        if human_escalation_decision is not None:
            why["human_escalation"] = {
                "action": str(getattr(human_escalation_decision, "action", "continue")),
                "severity": str(getattr(human_escalation_decision, "severity", "info")),
                "manual_review_required": bool(getattr(human_escalation_decision, "manual_review_required", False)),
                "disagreement_score": float(getattr(human_escalation_decision, "disagreement_score", 0.0) or 0.0),
                "reasons": list(getattr(human_escalation_decision, "reasons", []) or []),
            }
            escalation_action = str(getattr(human_escalation_decision, "action", "continue"))
            if escalation_action == "flatten_only":
                no_trade_reason = no_trade_reason or "human_escalation_flatten_only"
                reasons.append("human_escalation_flatten_only")
            elif escalation_action == "manual_review":
                no_trade_reason = no_trade_reason or "human_escalation_manual_review"
                reasons.append("human_escalation_manual_review")
        if quantum_state is not None:
            collapse = quantum_state.collapse_decision
            uncertainty = max(uncertainty, float(collapse.uncertainty))
            size_multiplier = min(size_multiplier, float(collapse.size_multiplier or 0.0) or 1.0)
            why["quantum_state"] = {
                "dominant_state": quantum_state.scenario_tree.dominant_state,
                "recommended_action": collapse.recommended_action,
                "side": collapse.side,
                "action_score": collapse.action_score,
                "no_trade_probability": collapse.no_trade_probability,
                "execution_fragility_score": collapse.execution_fragility_score,
                "uncertainty": collapse.uncertainty,
                "branch_disagreement_score": float(getattr(collapse, "branch_disagreement_score", 0.0)),
                "scenario_drift_score": float(getattr(collapse, "scenario_drift_score", 0.0)),
                "reasons": list(collapse.reasons),
                "top_states": dict(getattr(getattr(quantum_state, "collapse_context", object()), "top_states", {}) or {}),
                "heuristic": quantum_state.heuristic,
            }
            if collapse.recommended_action == "no_trade":
                no_trade_reason = no_trade_reason or "quantum_no_trade"
                reasons.append("quantum_no_trade")
            elif collapse.side is not None and abs(combined) > 1e-9:
                implied_side = "buy" if combined > 0 else "sell"
                if implied_side != collapse.side:
                    no_trade_reason = no_trade_reason or "quantum_signal_conflict"
                    reasons.append("quantum_signal_conflict")
            if collapse.execution_fragility_score >= 0.75:
                no_trade_reason = no_trade_reason or "execution_fragility"
                reasons.append("execution_fragility")
            if float(getattr(collapse, "branch_disagreement_score", 0.0)) >= 0.6:
                no_trade_reason = no_trade_reason or "quantum_branch_disagreement"
                reasons.append("quantum_branch_disagreement")
            if float(getattr(collapse, "scenario_drift_score", 0.0)) >= 0.65:
                no_trade_reason = no_trade_reason or "quantum_scenario_drift"
                reasons.append("quantum_scenario_drift")
        if edge_immunity_decision is not None:
            report = edge_immunity_decision.report
            size_multiplier = min(size_multiplier, float(report.recommended_size_multiplier))
            why["edge_immunity"] = {
                "action": edge_immunity_decision.action,
                "reason": edge_immunity_decision.reason,
                "edge_survival_ratio": report.edge_survival_ratio,
                "fragility_index": report.fragility_index,
                "self_impact_penalty_bps": report.self_impact_penalty_bps,
                "reality_gap_score": report.reality_gap_score,
                "wait_value_score": report.wait_value_score,
                "recommended_execution_style": report.recommended_execution_style,
                "dominant_failure_modes": list(report.dominant_failure_modes),
            }
            if edge_immunity_decision.action == "no_trade":
                no_trade_reason = no_trade_reason or "edge_fragility"
                reasons.append("edge_fragility")
            elif edge_immunity_decision.action == "wait":
                no_trade_reason = no_trade_reason or "wait_dominance"
                reasons.append("wait_dominance")
            elif edge_immunity_decision.action == "trade_smaller":
                reasons.append("trade_smaller_due_to_fragility")
        if inventory_context is not None:
            why["inventory"] = dict(inventory_context)
        if profitability_context is not None:
            why["profitability"] = dict(profitability_context)
            round_trip = profitability_context.get("round_trip", {})
            release = profitability_context.get("capital_release", {})
            action = str(round_trip.get("action", "trade_now"))
            size_multiplier = min(size_multiplier, float(round_trip.get("recommended_size_multiplier", 1.0)))
            if action == "no_trade":
                no_trade_reason = no_trade_reason or "round_trip_profitability_guard"
                reasons.append("round_trip_profitability_guard")
            elif action == "wait":
                no_trade_reason = no_trade_reason or "wait_for_better_round_trip"
                reasons.append("wait_for_better_round_trip")
            elif action == "trade_smaller":
                reasons.append("trade_smaller_due_to_round_trip")
            if bool(release.get("allowed", False)) and str(release.get("action", "")) == "partial_exit":
                no_trade_reason = no_trade_reason or "capital_release_priority"
                reasons.append("capital_release_priority")
        spre_decision = self.spre_engine.evaluate(
            symbol=fc.symbol,
            ts=fc.ts,
            combined_signal=combined,
            expected_edge_bps=expected_edge_bps,
            expected_cost_bps=expected_cost_bps,
            uncertainty=uncertainty,
            quantum_state=quantum_state,
            edge_immunity_decision=edge_immunity_decision,
            profitability_context=profitability_context,
            event_intelligence_report=event_intelligence_report,
            synthetic_affect_state=synthetic_affect_state,
            execution_simulation_report=execution_simulation_report,
        )
        why["spre"] = {
            "dominant_action": spre_decision.dominant_action,
            "side": spre_decision.side,
            "size_multiplier": spre_decision.size_multiplier,
            "regret_score": spre_decision.regret_score,
            "no_trade_quality": spre_decision.no_trade_quality,
            "narrative": spre_decision.narrative,
            "reasons": list(spre_decision.reasons),
            "heuristic": spre_decision.heuristic,
            "chosen_survival_ratio": float(spre_decision.metadata.get("chosen_survival_ratio", 0.0) or 0.0),
            "action_gap_bps": float(spre_decision.metadata.get("action_gap_bps", 0.0) or 0.0),
            "dominant_failure_modes": list(spre_decision.metadata.get("dominant_failure_modes", []) or []),
            "action_rankings": list(spre_decision.metadata.get("action_rankings", []) or []),
            "internal_action": str(spre_decision.metadata.get("internal_action", spre_decision.dominant_action)),
            "ambiguity_penalty": float(spre_decision.metadata.get("ambiguity_penalty", 0.0) or 0.0),
            "action_scores": {str(k): float(v) for k, v in dict(spre_decision.metadata.get("dominance_scores", {}) or {}).items()},
        }
        if spre_decision.dominant_action == "no_trade":
            no_trade_reason = no_trade_reason or "spre_no_trade_dominance"
            reasons.append("spre_no_trade_dominance")
        elif spre_decision.dominant_action == "wait":
            no_trade_reason = no_trade_reason or "spre_wait_dominance"
            reasons.append("spre_wait_dominance")
        elif spre_decision.dominant_action == "trade_smaller":
            size_multiplier = min(size_multiplier, float(spre_decision.size_multiplier))
            reasons.append("spre_trade_smaller")

        shadow_rival = self.shadow_rival_service.evaluate(
            symbol=fc.symbol,
            ts=fc.ts,
            spre_decision=spre_decision,
            quantum_state=quantum_state,
            edge_immunity_decision=edge_immunity_decision,
            event_intelligence_report=event_intelligence_report,
            synthetic_affect_state=synthetic_affect_state,
            execution_simulation_report=execution_simulation_report,
        )
        why["shadow_rival"] = {
            "action": shadow_rival.action,
            "allowed": shadow_rival.allowed,
            "critique_score": shadow_rival.critique_score,
            "reasons": list(shadow_rival.reasons),
            "narrative": shadow_rival.narrative,
            "heuristic": shadow_rival.heuristic,
            "thesis_break_score": float(shadow_rival.metadata.get("thesis_break_score", 0.0) or 0.0),
            "ambiguity_score": float(shadow_rival.metadata.get("ambiguity_score", 0.0) or 0.0),
            "kill_path_score": float(shadow_rival.metadata.get("kill_path_score", 0.0) or 0.0),
            "wait_dominance_score": float(shadow_rival.metadata.get("wait_dominance_score", 0.0) or 0.0),
            "action_gap_bps": float(shadow_rival.metadata.get("action_gap_bps", 0.0) or 0.0),
            "chosen_survival_ratio": float(shadow_rival.metadata.get("chosen_survival_ratio", 0.0) or 0.0),
            "dominant_failure_modes": list(shadow_rival.metadata.get("dominant_failure_modes", []) or []),
        }
        if shadow_rival.action == "no_trade":
            no_trade_reason = no_trade_reason or "shadow_rival_veto"
            reasons.append("shadow_rival_veto")
        elif shadow_rival.action == "wait":
            no_trade_reason = no_trade_reason or "shadow_rival_wait"
            reasons.append("shadow_rival_wait")
        elif shadow_rival.action == "trade_smaller":
            size_multiplier = min(size_multiplier, 0.5)
            reasons.append("shadow_rival_size_cut")

        doctrine_report = self.decision_doctrine_service.evaluate(
            symbol=fc.symbol,
            ts=fc.ts,
            base_uncertainty=uncertainty,
            truth_context=truth_context,
            market_integrity_status=market_integrity_status,
            provider_capability=provider_capability,
            execution_quality=execution_quality,
            portfolio_allocation=portfolio_allocation,
            profitability_context=profitability_context,
            event_intelligence_report=event_intelligence_report,
            synthetic_affect_state=synthetic_affect_state,
            capital_sovereignty_decision=capital_sovereignty_decision,
            position_morph_plan=position_morph_plan,
            execution_simulation_report=execution_simulation_report,
            spre_decision=spre_decision,
            shadow_rival_report=shadow_rival,
            edge_immunity_decision=edge_immunity_decision,
            quantum_state=quantum_state,
            mastermind_advisory=mastermind_advisory,
        )
        why["decision_doctrine"] = {
            "recommended_action": doctrine_report.recommended_action,
            "size_multiplier": doctrine_report.size_multiplier,
            "truth_strength": doctrine_report.truth_strength,
            "survival_score": doctrine_report.survival_score,
            "robustness_score": doctrine_report.robustness_score,
            "execution_survivability_score": doctrine_report.execution_survivability_score,
            "capital_freedom_score": doctrine_report.capital_freedom_score,
            "uncertainty_pressure": doctrine_report.uncertainty_pressure,
            "partial_truth_penalty": doctrine_report.partial_truth_penalty,
            "regret_pressure": doctrine_report.regret_pressure,
            "reasons": list(doctrine_report.reasons),
            "partial": doctrine_report.partial,
            "metadata": dict(doctrine_report.metadata),
        }
        uncertainty = max(uncertainty, float(doctrine_report.uncertainty_pressure))
        doctrine_action = doctrine_report.recommended_action
        if doctrine_action == "no_trade":
            no_trade_reason = no_trade_reason or "decision_doctrine_no_trade"
            reasons.append("decision_doctrine_no_trade")
        elif doctrine_action == "wait":
            no_trade_reason = no_trade_reason or "decision_doctrine_wait"
            reasons.append("decision_doctrine_wait")
        elif doctrine_action == "probe":
            size_multiplier = min(size_multiplier, float(doctrine_report.size_multiplier), 0.25)
            reasons.append("decision_doctrine_probe")
        elif doctrine_action == "trade_smaller":
            size_multiplier = min(size_multiplier, float(doctrine_report.size_multiplier), 0.5)
            reasons.append("decision_doctrine_trade_smaller")
        if no_trade_reason is not None:
            return PolicyDecision(
                symbol=fc.symbol,
                ts=fc.ts,
                trade_allowed=False,
                expected_edge_bps=expected_edge_bps,
                expected_cost_bps=expected_cost_bps,
                expected_slippage_bps=slippage_bps,
                confidence=fc.confidence,
                uncertainty=uncertainty,
                regime_fit=regime_fit,
                capacity_limit=capacity_limit,
                why=why,
                profitability={} if profitability_context is None else dict(profitability_context),
                inventory={} if inventory_context is None else dict(inventory_context),
                no_trade=NoTradeDecision(
                    symbol=fc.symbol,
                    ts=fc.ts,
                    reason=no_trade_reason,
                    reasons=sorted(set(reasons)),
                    expected_edge_bps=expected_edge_bps,
                    expected_cost_bps=expected_cost_bps,
                    confidence=fc.confidence,
                    uncertainty=uncertainty,
                    metadata=why,
                ),
            )

        side = "buy" if combined > 0 else "sell"
        if self.long_only and side == "sell":
            return PolicyDecision(
                symbol=fc.symbol,
                ts=fc.ts,
                trade_allowed=False,
                expected_edge_bps=expected_edge_bps,
                expected_cost_bps=expected_cost_bps,
                expected_slippage_bps=slippage_bps,
                confidence=fc.confidence,
                uncertainty=uncertainty,
                regime_fit=regime_fit,
                capacity_limit=capacity_limit,
                why={**why, "doctrine_target": {"long_only": True, "policy_block": "no_new_short_exposure"}},
                profitability={} if profitability_context is None else dict(profitability_context),
                inventory={} if inventory_context is None else dict(inventory_context),
                no_trade=NoTradeDecision(
                    symbol=fc.symbol,
                    ts=fc.ts,
                    reason="long_only_no_new_short_exposure",
                    reasons=sorted(set(reasons + ["long_only_no_new_short_exposure"])),
                    expected_edge_bps=expected_edge_bps,
                    expected_cost_bps=expected_cost_bps,
                    confidence=fc.confidence,
                    uncertainty=uncertainty,
                    metadata=why,
                ),
            )
        target = min(abs(combined) * max(0.0, size_multiplier), self.settings.base_risk_budget)
        return PolicyDecision(
            symbol=fc.symbol,
            ts=fc.ts,
            trade_allowed=True,
            side=side,
            target_notional=target,
            expected_edge_bps=expected_edge_bps,
            expected_cost_bps=expected_cost_bps,
            expected_slippage_bps=slippage_bps,
            expected_adverse_excursion_bps=max(0.0, fc.sigma * 10000.0),
            expected_favorable_excursion_bps=max(0.0, abs(fc.mu) * 10000.0),
            confidence=fc.confidence,
            uncertainty=uncertainty,
            regime_fit=regime_fit,
            capacity_limit=capacity_limit,
            why=why,
            profitability={} if profitability_context is None else dict(profitability_context),
            inventory={} if inventory_context is None else dict(inventory_context),
        )

    def make_intent(self, fc: Forecast, features: dict[str, float], fee_bps: float, slippage_bps: float) -> OrderIntent | None:
        legacy_spre = self.spre_engine
        legacy_shadow = self.shadow_rival_service
        legacy_doctrine = self.decision_doctrine_service
        self.spre_engine = SimpleNamespace(
            evaluate=lambda **kwargs: SimpleNamespace(
                dominant_action="trade_now",
                side="buy" if float(kwargs.get("combined_signal", 0.0) or 0.0) >= 0.0 else "sell",
                size_multiplier=1.0,
                regret_score=0.0,
                no_trade_quality=0.0,
                narrative="legacy_make_intent_compat",
                reasons=["legacy_make_intent_compat"],
                heuristic=True,
                metadata={},
            )
        )
        self.shadow_rival_service = SimpleNamespace(
            evaluate=lambda **kwargs: SimpleNamespace(
                action="continue",
                allowed=True,
                critique_score=0.0,
                reasons=["legacy_make_intent_compat"],
                narrative="legacy_make_intent_compat",
                heuristic=True,
                metadata={},
            )
        )
        self.decision_doctrine_service = SimpleNamespace(
            evaluate=lambda **kwargs: SimpleNamespace(
                recommended_action="continue",
                size_multiplier=1.0,
                truth_strength=1.0,
                survival_score=1.0,
                robustness_score=1.0,
                execution_survivability_score=1.0,
                capital_freedom_score=1.0,
                uncertainty_pressure=0.0,
                partial_truth_penalty=0.0,
                regret_pressure=0.0,
                reasons=["legacy_make_intent_compat"],
                partial=False,
                metadata={},
            )
        )
        try:
            decision = self.evaluate_decision(fc, features, fee_bps, slippage_bps)
        finally:
            self.spre_engine = legacy_spre
            self.shadow_rival_service = legacy_shadow
            self.decision_doctrine_service = legacy_doctrine
        if not decision.trade_allowed or decision.side is None:
            return None
        legacy_why = dict(decision.why)
        legacy_why.pop("spre", None)
        legacy_why.pop("shadow_rival", None)
        legacy_why.pop("decision_doctrine", None)
        return OrderIntent(
            symbol=decision.symbol,
            side=decision.side,
            target_notional=decision.target_notional,
            why=legacy_why,
        )

    def update_allocator(self, strategy_pnl_bps: dict[str, float]) -> None:
        for s, pnl in strategy_pnl_bps.items():
            self.allocator.update_performance(s, pnl)
        self.allocator.step_cooldowns()
