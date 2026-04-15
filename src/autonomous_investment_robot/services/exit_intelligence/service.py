from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import ExitIntelligenceReport


class ExitIntelligenceService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def analyze(
        self,
        *,
        inventory_state: Any | None,
        profitability_context: dict[str, Any] | None,
        market: Any,
        execution_result: Any | None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        inventory_pressure = 0.0 if inventory_state is None else max(
            0.0,
            min(
                1.0,
                float(getattr(inventory_state, "stale_inventory_score", 0.0) or 0.0) * 0.50
                + float(getattr(inventory_state, "opportunity_cost_pressure", 0.0) or 0.0) * 0.25
                + float(getattr(inventory_state, "execution_fragility_pressure", 0.0) or 0.0) * 0.25,
            ),
        )
        hold_time_minutes = 0.0 if inventory_state is None else float(getattr(inventory_state, "weighted_age_seconds", 0.0) or 0.0) / 60.0
        hold_time_target_minutes = min(float(self.settings.performance_targets.max_inventory_age_minutes), 240.0)
        adverse_excursion_bps = max(0.0, float(getattr(getattr(market, "forecast", None), "sigma", 0.0) or 0.0) * 10000.0)
        favorable_excursion_bps = max(0.0, abs(float(getattr(getattr(market, "forecast", None), "mu", 0.0) or 0.0)) * 10000.0)
        round_trip = dict((profitability_context or {}).get("round_trip", {}) or {})
        preferred_exit_family = "alpha_capture_exit"
        root_cause = "alpha_capture"
        reasons: list[str] = []
        if round_trip.get("action") == "trade_smaller":
            preferred_exit_family = "partial_take_profit_exit"
            root_cause = "profitability_partial_exit"
            reasons.append("round_trip_trade_smaller")
        if inventory_pressure >= 0.70:
            preferred_exit_family = "forced_inventory_cleanup_exit"
            root_cause = "inventory_pressure"
            reasons.append("inventory_pressure_high")
        elif hold_time_minutes > hold_time_target_minutes:
            preferred_exit_family = "time_stop_exit"
            root_cause = "inventory_age"
            reasons.append("inventory_age_high")
        elif adverse_excursion_bps > favorable_excursion_bps * 1.25:
            preferred_exit_family = "adverse_microstructure_exit"
            root_cause = "adverse_excursion"
            reasons.append("adverse_excursion_dominant")
        elif str(getattr(getattr(market, "regime_assessment", None), "label", "") or "") in {"news_chaos", "liquidity_vacuum"}:
            preferred_exit_family = "regime_invalidation_exit"
            root_cause = "regime_invalidation"
            reasons.append("regime_invalidation")
        if execution_result is not None and "reject" in str(getattr(execution_result, "status", "")).lower():
            reasons.append("last_execution_rejected")
        trade_lifecycle_score = max(0.0, min(1.0, favorable_excursion_bps / max(adverse_excursion_bps + 1.0, 1.0)))
        report = ExitIntelligenceReport(
            ts=now,
            preferred_exit_family=preferred_exit_family,
            inventory_pressure=inventory_pressure,
            hold_time_minutes=hold_time_minutes,
            hold_time_target_minutes=hold_time_target_minutes,
            adverse_excursion_bps=adverse_excursion_bps,
            favorable_excursion_bps=favorable_excursion_bps,
            trade_lifecycle_score=trade_lifecycle_score,
            root_cause=root_cause,
            reasons=reasons,
            metadata={
                "shadow_only_cleanup_exit": preferred_exit_family in {"forced_inventory_cleanup_exit"},
                "normal_sell_floor_preserved": True,
            },
        )
        payload = asdict(report)
        return {
            "exit_decision_log": payload,
            "inventory_aging_report": {
                "ts": payload["ts"],
                "hold_time_minutes": hold_time_minutes,
                "hold_time_target_minutes": hold_time_target_minutes,
            },
            "realized_exit_quality_report": {
                "ts": payload["ts"],
                "trade_lifecycle_score": trade_lifecycle_score,
                "preferred_exit_family": preferred_exit_family,
            },
            "exit_reason_distribution": {
                "ts": payload["ts"],
                "preferred_exit_family": preferred_exit_family,
                "reasons": reasons,
            },
            "exit_ladder_report": {
                "ts": payload["ts"],
                "ladder": ["partial_take_profit_exit", "trailing_profit_exit", "time_stop_exit", "regime_invalidation_exit"],
            },
            "hold_time_optimization_report": {
                "ts": payload["ts"],
                "current_hold_minutes": hold_time_minutes,
                "target_hold_minutes": hold_time_target_minutes,
            },
            "inventory_pressure_report": {
                "ts": payload["ts"],
                "inventory_pressure": inventory_pressure,
                "stale_inventory_score": 0.0 if inventory_state is None else float(getattr(inventory_state, "stale_inventory_score", 0.0) or 0.0),
            },
            "adverse_excursion_report": {
                "ts": payload["ts"],
                "adverse_excursion_bps": adverse_excursion_bps,
                "favorable_excursion_bps": favorable_excursion_bps,
            },
            "trade_lifecycle_scoring": {
                "ts": payload["ts"],
                "trade_lifecycle_score": trade_lifecycle_score,
            },
            "post_trade_root_cause_report": {
                "ts": payload["ts"],
                "root_cause": root_cause,
                "reasons": reasons,
            },
        }
