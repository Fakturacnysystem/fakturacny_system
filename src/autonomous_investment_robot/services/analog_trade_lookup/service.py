from __future__ import annotations

from typing import Any

from autonomous_investment_robot.core.contracts import AnalogTradeMatch, TradeEpisode


class AnalogTradeLookup:
    def __init__(self, memory: Any) -> None:
        self.memory = memory

    def lookup(
        self,
        *,
        symbol: str,
        regime_label: str,
        side: str,
        truth_confidence_state: str,
        execution_quality_state: str,
        event_context: dict[str, Any] | None = None,
        top_k: int = 3,
    ) -> list[AnalogTradeMatch]:
        event_context = dict(event_context or {})
        matches: list[AnalogTradeMatch] = []
        for episode in self.memory.recent(100):
            score = 0.0
            reasons: list[str] = []
            if episode.symbol == symbol:
                score += 0.3
                reasons.append("same_symbol")
            if episode.regime_label == regime_label:
                score += 0.25
                reasons.append("same_regime")
            if episode.side == side:
                score += 0.15
                reasons.append("same_side")
            if episode.truth_confidence_state == truth_confidence_state:
                score += 0.15
                reasons.append("same_truth_state")
            if episode.execution_quality_state == execution_quality_state:
                score += 0.1
                reasons.append("same_execution_state")
            if event_context and episode.event_context:
                overlap = len(set(event_context.keys()) & set(episode.event_context.keys()))
                if overlap:
                    score += min(0.05, overlap * 0.02)
                    reasons.append("event_context_overlap")
            if score > 0.0:
                matches.append(
                    AnalogTradeMatch(
                        episode_id=episode.episode_id,
                        similarity_score=min(1.0, score),
                        reasons=reasons,
                        metadata={"result": episode.result, "realized_pnl": episode.realized_pnl, "failure_mode": episode.failure_mode},
                    )
                )
        matches.sort(key=lambda item: item.similarity_score, reverse=True)
        return matches[:top_k]
