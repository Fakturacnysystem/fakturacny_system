from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import PlaybookCandidate


class PlaybookFrameworkService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._definitions = {
            "trend_follow_entry": {"regimes": {"trend", "strong_trend", "weak_trend"}, "execution": "maker_first", "exit_family": "trailing_profit_exit"},
            "mean_reversion_entry": {"regimes": {"mean_reversion", "chop", "low_vol_chop"}, "execution": "passive_limit", "exit_family": "alpha_capture_exit"},
            "breakout_continuation": {"regimes": {"breakout", "high_vol_expansion", "vol_expansion"}, "execution": "timed_limit", "exit_family": "trailing_profit_exit"},
            "volatility_expansion": {"regimes": {"high_vol_expansion", "vol_expansion", "news_chaos"}, "execution": "adaptive_limit", "exit_family": "regime_invalidation_exit"},
            "pullback_reentry": {"regimes": {"trend", "weak_trend", "fake_breakout"}, "execution": "maker_first", "exit_family": "partial_take_profit_exit"},
            "inventory_unwind": {"regimes": {"trend", "mean_reversion", "dead_market", "liquidity_vacuum"}, "execution": "reduce_only_passive", "exit_family": "forced_inventory_cleanup_exit"},
            "profit_capture_exit": {"regimes": {"trend", "mean_reversion", "breakout"}, "execution": "reduce_only_passive", "exit_family": "alpha_capture_exit"},
        }

    def evaluate(
        self,
        *,
        symbol: str,
        forecast: Any,
        regime_assessment: Any | None,
        features: dict[str, float],
        execution_quality: Any | None,
        inventory_state: Any | None,
        expectancy_report: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        regime_label = str(getattr(regime_assessment, "label", "") or getattr(forecast, "regime", "unavailable")).lower()
        confidence_calibration = float(expectancy_report.get("metadata", {}).get("confidence_calibration", 0.0) or 0.0)
        candidates: list[PlaybookCandidate] = []
        for playbook, definition in self._definitions.items():
            compatible = regime_label in definition["regimes"]
            live_enabled = compatible and playbook not in set(self.settings.playbooks.shadow_only_playbooks)
            base_edge_bps = abs(float(getattr(forecast, "mu", 0.0) or 0.0)) * 10000.0
            volatility_penalty = max(0.0, float(getattr(forecast, "sigma", 0.0) or 0.0) * 1000.0 - 5.0)
            spread_penalty = max(0.0, float(features.get("spread_proxy", 0.0) or 0.0) * 10000.0)
            inventory_pressure = max(0.0, float(getattr(inventory_state, "stale_inventory_score", 0.0) or 0.0)) if inventory_state is not None else 0.0
            execution_penalty = 0.0 if execution_quality is None else max(0.0, float(getattr(execution_quality, "adverse_selection_risk", 0.0) or 0.0) * 20.0)
            gross_edge_bps = max(0.0, base_edge_bps * (1.05 if compatible else 0.65))
            net_edge_bps = max(0.0, gross_edge_bps - spread_penalty - volatility_penalty - execution_penalty)
            if playbook == "inventory_unwind":
                gross_edge_bps = inventory_pressure * 25.0
                net_edge_bps = max(0.0, gross_edge_bps - execution_penalty)
            if playbook == "profit_capture_exit":
                gross_edge_bps = max(gross_edge_bps, float(expectancy_report.get("avg_win_bps", 0.0) or 0.0))
                net_edge_bps = max(0.0, gross_edge_bps - execution_penalty)
            confidence = max(0.0, min(1.0, float(getattr(forecast, "confidence", 0.0) or 0.0) * (1.0 if compatible else 0.65)))
            quality_of_edge = max(0.0, min(1.0, net_edge_bps / 40.0 + confidence * 0.35))
            opportunity_decay = max(0.0, min(1.0, 1.0 - float(self.settings.playbooks.default_opportunity_half_life_s) / max(float(self.settings.playbooks.default_opportunity_half_life_s), 1.0 + abs(float(features.get("seconds_since_distinct_book_change", 0.0) or 0.0)))))
            capital_efficiency = max(0.0, min(1.0, 0.5 + net_edge_bps / 80.0 - inventory_pressure * 0.2))
            hold_minutes = max(5.0, min(720.0, 30.0 + abs(float(getattr(forecast, "sigma", 0.0) or 0.0)) * 6000.0))
            disable_reasons = []
            if not compatible:
                disable_reasons.append("regime_incompatible")
            if confidence < self.settings.policy.confidence_threshold:
                disable_reasons.append("confidence_below_threshold")
            if net_edge_bps <= 0.0:
                disable_reasons.append("net_edge_non_positive")
            side = "sell" if playbook in {"inventory_unwind", "profit_capture_exit"} else "buy"
            target_notional = 0.0 if disable_reasons else min(
                float(self.settings.policy.base_risk_budget),
                max(0.0, net_edge_bps) * float(self.settings.policy.base_risk_budget) / 40.0,
            )
            candidates.append(
                PlaybookCandidate(
                    symbol=symbol,
                    playbook=playbook,
                    ts=now,
                    live_enabled=live_enabled,
                    expected_gross_edge_bps=gross_edge_bps,
                    expected_net_edge_bps=net_edge_bps,
                    confidence=confidence,
                    quality_of_edge=quality_of_edge,
                    opportunity_decay=opportunity_decay,
                    capital_efficiency=capital_efficiency,
                    hold_minutes=hold_minutes,
                    execution_preference=str(definition["execution"]),
                    exit_family=str(definition["exit_family"]),
                    side=side,
                    target_notional=target_notional,
                    cooldown_active=False,
                    disable_reasons=disable_reasons,
                    reasons=[
                        f"regime:{regime_label}",
                        f"confidence:{confidence:.3f}",
                        f"net_edge_bps:{net_edge_bps:.2f}",
                    ],
                    metadata={
                        "compatible_regimes": sorted(definition["regimes"]),
                        "confidence_calibration_state": confidence_calibration,
                        "shadow_only": playbook in set(self.settings.playbooks.shadow_only_playbooks),
                    },
                )
            )
        candidates.sort(key=lambda item: (item.live_enabled, item.expected_net_edge_bps, item.quality_of_edge), reverse=True)
        serialized = [asdict(candidate) for candidate in candidates]
        return {
            "candidates": serialized,
            "playbook_candidate_log": {
                "ts": now.isoformat(),
                "symbol": symbol,
                "candidates": serialized,
            },
            "playbook_expectancy_summary": {
                "ts": now.isoformat(),
                "symbol": symbol,
                "expectancy_bps": float(expectancy_report.get("net_expectancy_bps", 0.0) or 0.0),
                "playbooks": {
                    candidate.playbook: {
                        "expected_net_edge_bps": candidate.expected_net_edge_bps,
                        "quality_of_edge": candidate.quality_of_edge,
                        "capital_efficiency": candidate.capital_efficiency,
                    }
                    for candidate in candidates
                },
            },
            "playbook_disable_reasons": {
                "ts": now.isoformat(),
                "disable_reasons": {candidate.playbook: list(candidate.disable_reasons) for candidate in candidates if candidate.disable_reasons},
            },
            "playbook_shadow_evaluation": {
                "ts": now.isoformat(),
                "shadow_only": [candidate.playbook for candidate in candidates if not candidate.live_enabled],
                "live_candidates": [candidate.playbook for candidate in candidates if candidate.live_enabled],
            },
            "playbook_confidence_calibration": {
                "ts": now.isoformat(),
                "symbol": symbol,
                "confidence_calibration_state": confidence_calibration,
                "playbooks": {candidate.playbook: candidate.confidence for candidate in candidates},
            },
            "playbook_opportunity_decay_report": {
                "ts": now.isoformat(),
                "symbol": symbol,
                "opportunity_decay": {candidate.playbook: candidate.opportunity_decay for candidate in candidates},
            },
        }

