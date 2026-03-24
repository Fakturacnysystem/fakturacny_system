from __future__ import annotations

from datetime import datetime
from typing import Any

from autonomous_investment_robot.core.contracts import CounterfactualReview


class CounterfactualEvaluator:
    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        chosen_action: str,
        realized_pnl: float,
        profitability_context: dict[str, Any] | None,
        edge_immunity_context: dict[str, Any] | None,
        quantum_context: dict[str, Any] | None,
        similar_episodes: list[Any] | None,
    ) -> CounterfactualReview:
        profitability_context = dict(profitability_context or {})
        edge_immunity_context = dict(edge_immunity_context or {})
        quantum_context = dict(quantum_context or {})
        similar_episodes = list(similar_episodes or [])
        reasons: list[str] = []
        best_alternative = "hold"
        if realized_pnl < 0.0:
            best_alternative = "no_trade"
            reasons.append("negative_realized_pnl")
        if str(profitability_context.get("round_trip", {}).get("action", "")) in {"wait", "no_trade"}:
            best_alternative = str(profitability_context.get("round_trip", {}).get("action"))
            reasons.append("profitability_counterfactual")
        if str(edge_immunity_context.get("action", "")) in {"wait", "no_trade"}:
            best_alternative = str(edge_immunity_context.get("action"))
            reasons.append("edge_counterfactual")
        if float(quantum_context.get("no_trade_probability", 0.0) or 0.0) >= 0.7:
            best_alternative = "no_trade"
            reasons.append("quantum_counterfactual")
        if similar_episodes:
            negative_matches = [m for m in similar_episodes if float(getattr(m, "metadata", {}).get("realized_pnl", 0.0) or 0.0) < 0.0]
            if len(negative_matches) >= max(1, len(similar_episodes) // 2):
                best_alternative = "no_trade"
                reasons.append("analog_episode_loss_cluster")
        realized_regret = max(0.0, -realized_pnl) if best_alternative in {"no_trade", "wait", "hold"} else 0.0
        avoided_regret = max(0.0, realized_pnl) if best_alternative != chosen_action and realized_pnl > 0.0 else 0.0
        return CounterfactualReview(
            symbol=symbol,
            ts=ts,
            chosen_action=chosen_action,
            best_alternative_action=best_alternative,
            realized_regret=realized_regret,
            avoided_regret=avoided_regret,
            similar_episodes=list(similar_episodes),
            reasons=sorted(set(reasons)),
            metadata={"realized_pnl": realized_pnl},
        )
