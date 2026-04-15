from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import PerformanceTargetTranslationReport


class PerformanceTargetTranslationService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def translate(
        self,
        *,
        capital_envelope: dict[str, Any],
        expectancy: dict[str, Any] | None,
        throughput: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        throughput = throughput or {}
        targets = self.settings.performance_targets
        target_monthly_return_pct = float(targets.monthly_return_pct)
        required_daily_return_pct = target_monthly_return_pct / 30.0
        required_capital_utilization_pct = max(float(targets.capital_utilization_pct), 1.0)
        target_round_trips_per_day = max(float(targets.round_trips_per_day), 0.1)
        utilization_fraction = max(required_capital_utilization_pct / 100.0, 0.01)
        required_net_bps_per_trade = (required_daily_return_pct / 100.0) / utilization_fraction / target_round_trips_per_day * 10000.0

        current_deployment_notional = max(0.0, float(capital_envelope.get("live_deployment_cap", 0.0) or 0.0))
        total_equity = max(0.0, float(capital_envelope.get("total_equity", 0.0) or 0.0))
        current_capital_utilization_pct = 0.0 if total_equity <= 0.0 else current_deployment_notional / total_equity * 100.0
        required_deployment_notional = total_equity * utilization_fraction

        expectancy_meta = {} if expectancy is None else dict(expectancy.get("metadata", {}) or {})
        current_expectancy_bps = 0.0 if expectancy is None else float(expectancy.get("net_expectancy_bps", 0.0) or 0.0)
        current_fill_rate = 0.0 if expectancy is None else float(expectancy_meta.get("fill_rate", 0.0) or 0.0)
        current_maker_ratio = 0.0 if expectancy is None else float(expectancy_meta.get("maker_ratio", 0.0) or 0.0)
        current_round_trips = float(throughput.get("fills", 0.0) or 0.0) / 2.0
        current_round_trips = max(current_round_trips, float(expectancy_meta.get("round_trips_per_day", 0.0) or 0.0) if expectancy is not None else 0.0)

        gaps = {
            "net_bps_per_trade_gap": required_net_bps_per_trade - current_expectancy_bps,
            "capital_utilization_gap_pct": required_capital_utilization_pct - current_capital_utilization_pct,
            "fill_rate_gap": float(targets.fill_rate) - current_fill_rate,
            "maker_ratio_gap": float(targets.maker_ratio) - current_maker_ratio,
            "round_trips_per_day_gap": target_round_trips_per_day - current_round_trips,
            "expectancy_floor_gap_bps": float(targets.expectancy_bps_floor) - current_expectancy_bps,
        }
        theoretically_implausible = bool(
            required_net_bps_per_trade > 120.0
            or current_deployment_notional <= 0.0
            or current_capital_utilization_pct < required_capital_utilization_pct * 0.5
        )

        shortfall_components = [
            ("net_edge_shortfall", gaps["net_bps_per_trade_gap"]),
            ("utilization_shortfall", gaps["capital_utilization_gap_pct"]),
            ("turnover_shortfall", gaps["round_trips_per_day_gap"]),
            ("fill_quality_shortfall", gaps["fill_rate_gap"]),
        ]
        shortfall_components.sort(key=lambda item: item[1], reverse=True)
        dominant_shortfall = shortfall_components[0][0] if shortfall_components else "unknown"
        report = PerformanceTargetTranslationReport(
            ts=datetime.now(timezone.utc),
            target_monthly_return_pct=target_monthly_return_pct,
            required_daily_return_pct=required_daily_return_pct,
            target_round_trips_per_day=target_round_trips_per_day,
            required_net_bps_per_trade=required_net_bps_per_trade,
            required_capital_utilization_pct=required_capital_utilization_pct,
            required_deployment_notional=required_deployment_notional,
            current_deployment_notional=current_deployment_notional,
            current_capital_utilization_pct=current_capital_utilization_pct,
            theoretically_implausible=theoretically_implausible,
            edge_shortfall_explanation=dominant_shortfall,
            gaps=gaps,
            metadata={
                "current_expectancy_bps": current_expectancy_bps,
                "current_fill_rate": current_fill_rate,
                "current_maker_ratio": current_maker_ratio,
                "current_round_trips_per_day": current_round_trips,
                "target_expectancy_floor_bps": float(targets.expectancy_bps_floor),
            },
        )
        translation = asdict(report)
        gap_report = {
            "ts": translation["ts"],
            "target_monthly_return_pct": target_monthly_return_pct,
            "theoretically_implausible_under_current_capital_envelope": theoretically_implausible,
            "gaps": gaps,
            "current_metrics": {
                "net_expectancy_bps": current_expectancy_bps,
                "capital_utilization_pct": current_capital_utilization_pct,
                "fill_rate": current_fill_rate,
                "maker_ratio": current_maker_ratio,
                "round_trips_per_day": current_round_trips,
            },
            "target_metrics": {
                "net_bps_per_trade": required_net_bps_per_trade,
                "capital_utilization_pct": required_capital_utilization_pct,
                "fill_rate": float(targets.fill_rate),
                "maker_ratio": float(targets.maker_ratio),
                "round_trips_per_day": target_round_trips_per_day,
            },
            "edge_shortfall_explanation": dominant_shortfall,
        }
        return translation, gap_report
