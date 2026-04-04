from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import MarketUniverseReport, PairScoreCard
from autonomous_investment_robot.services.universe.clustering import cluster_pairs
from autonomous_investment_robot.services.universe.scoring import eligibility_reasons, pair_score


class MarketUniverseService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def evaluate(
        self,
        *,
        symbol: str,
        microstructure: dict[str, Any],
        expectancy: dict[str, Any],
        capital_envelope: dict[str, Any],
        regime_label: str | None,
        provider_capability: Any | None = None,
    ) -> dict[str, Any]:
        configured_universe = list(self.settings.market_universe.pair_universe or self.settings.universe)
        if symbol not in configured_universe:
            configured_universe = [symbol, *configured_universe]
        fill_rate = float(expectancy.get("metadata", {}).get("fill_rate", 0.0) or expectancy.get("fill_rate", 0.0) or 0.0)
        expectancy_bps = float(expectancy.get("net_expectancy_bps", 0.0) or 0.0)
        capital_efficiency = float(capital_envelope.get("capital_efficiency_score", 0.0) or 0.0)
        spread_bps = float(microstructure.get("spread_bps", 0.0) or 0.0)
        depth_notional = float(microstructure.get("depth_notional", 0.0) or 0.0)
        volatility = float(microstructure.get("realized_volatility", 0.0) or 0.0)
        micro_quality = float(microstructure.get("microstructure_quality_score", 0.0) or 0.0)

        ranked_pairs: list[PairScoreCard] = []
        clusters = cluster_pairs(configured_universe) if bool(self.settings.market_universe.pair_clustering_enabled) else {}
        for candidate_symbol in configured_universe:
            active = candidate_symbol == symbol
            candidate_spread = spread_bps if active else max(spread_bps * 1.15, spread_bps + 3.0)
            candidate_depth = depth_notional if active else depth_notional * 0.75
            candidate_expectancy = expectancy_bps if active else expectancy_bps * 0.85
            candidate_fill = fill_rate if active else fill_rate * 0.80
            reasons = eligibility_reasons(
                spread_bps=candidate_spread,
                depth_notional=candidate_depth,
                expectancy_bps=candidate_expectancy,
                fill_rate=candidate_fill,
                settings=self.settings,
            )
            score = pair_score(
                spread_bps=candidate_spread,
                depth_notional=candidate_depth,
                realized_volatility=volatility,
                signal_stability=max(0.0, min(1.0, 1.0 - float(microstructure.get("stale_book_seconds", 0.0) or 0.0) / 20.0)),
                fill_quality=max(0.0, min(candidate_fill, 1.0)),
                execution_friction=max(0.0, min(candidate_spread / max(float(self.settings.market_universe.pair_max_spread_bps), 1.0), 1.0)),
                expectancy_bps=candidate_expectancy,
                reject_burden=1.0 if provider_capability is not None and str(getattr(provider_capability, "lifecycle_completeness", "")).startswith("partial") and not active else 0.0,
                capital_capacity=max(0.0, min(float(capital_envelope.get("pair_level_cap", 0.0) or 0.0) / max(float(self.settings.capital_envelope.max_pair_exposure_notional), 1.0), 1.0)),
                regime_compatibility=1.0 if regime_label not in {"dead_market", "liquidity_vacuum", "news_chaos"} else 0.25,
                capital_efficiency=capital_efficiency,
                microstructure_quality=micro_quality,
                crowding_penalty=0.0 if active else 0.10,
            )
            ranked_pairs.append(
                PairScoreCard(
                    symbol=candidate_symbol,
                    score=score,
                    eligible=not reasons,
                    active=active,
                    spread_quality=max(0.0, min(1.0, 1.0 - candidate_spread / max(float(self.settings.market_universe.pair_max_spread_bps), 1.0))),
                    depth_quality=max(0.0, min(1.0, candidate_depth / max(float(self.settings.market_universe.pair_min_depth_notional), 1.0))),
                    realized_volatility=volatility,
                    signal_stability=max(0.0, min(1.0, 1.0 - float(microstructure.get("stale_book_seconds", 0.0) or 0.0) / 20.0)),
                    fill_quality=max(0.0, min(candidate_fill, 1.0)),
                    execution_friction=max(0.0, min(candidate_spread / max(float(self.settings.market_universe.pair_max_spread_bps), 1.0), 1.0)),
                    expectancy_bps=candidate_expectancy,
                    reject_burden=0.0 if active else 0.10,
                    capital_capacity=max(0.0, min(float(capital_envelope.get("pair_level_cap", 0.0) or 0.0) / max(float(self.settings.capital_envelope.max_pair_exposure_notional), 1.0), 1.0)),
                    regime_compatibility=1.0 if regime_label not in {"dead_market", "liquidity_vacuum", "news_chaos"} else 0.25,
                    capital_efficiency=capital_efficiency,
                    microstructure_quality=micro_quality,
                    crowding_penalty=0.0 if active else 0.10,
                    reasons=reasons,
                    metadata={"cluster_keys": [key for key, members in clusters.items() if candidate_symbol in members]},
                )
            )
        ranked_pairs.sort(key=lambda card: (card.eligible, card.score, card.active), reverse=True)
        active_symbols = [card.symbol for card in ranked_pairs[: max(1, min(int(self.settings.market_universe.max_active_pairs), len(ranked_pairs)))]]
        report = MarketUniverseReport(
            ts=datetime.now(timezone.utc),
            active_symbols=active_symbols,
            ranked_pairs=ranked_pairs,
            clusters=clusters,
            rotation_reason="top_ranked_active_set_changed" if symbol not in active_symbols else "current_symbol_retained",
            metadata={
                "configured_universe": configured_universe,
                "regime_label": regime_label,
            },
        )
        ranked_payload = [asdict(card) for card in ranked_pairs]
        return {
            "pair_universe_snapshot": asdict(report),
            "pair_ranking_report": {
                "ts": report.ts.isoformat(),
                "active_symbols": active_symbols,
                "ranked_pairs": ranked_payload,
            },
            "pair_rotation_decisions": {
                "ts": report.ts.isoformat(),
                "selected_symbol": symbol,
                "recommended_symbols": active_symbols,
                "rotation_reason": report.rotation_reason,
            },
            "pair_cluster_report": {
                "ts": report.ts.isoformat(),
                "clusters": clusters,
            },
            "pair_admission_expulsion_report": {
                "ts": report.ts.isoformat(),
                "admitted": [card.symbol for card in ranked_pairs if card.eligible],
                "expelled": [card.symbol for card in ranked_pairs if not card.eligible],
                "reasons": {card.symbol: list(card.reasons) for card in ranked_pairs if card.reasons},
            },
            "venue_behavior_profile_report": {
                "ts": report.ts.isoformat(),
                "symbol_profiles": {
                    card.symbol: {
                        "score": card.score,
                        "spread_quality": card.spread_quality,
                        "depth_quality": card.depth_quality,
                        "execution_friction": card.execution_friction,
                        "microstructure_quality": card.microstructure_quality,
                    }
                    for card in ranked_pairs
                },
            },
        }
