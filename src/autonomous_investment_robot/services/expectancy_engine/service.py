from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import ExpectancyEngineReport


def _extract_bps(row: dict[str, Any]) -> float | None:
    for key in ("net_bps", "realized_pnl_bps", "pnl_bps", "return_bps"):
        value = row.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


class ExpectancyEngineService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def build(
        self,
        *,
        fills: list[dict[str, Any]],
        order_events: list[dict[str, Any]],
        trade_log: list[dict[str, Any]],
        ranked_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ranked_candidates = ranked_candidates or []
        window = max(1, int(self.settings.expectancy.rolling_window_trades))
        trade_rows = trade_log[-window:]
        realized_bps = [_extract_bps(row) for row in trade_rows]
        realized_bps = [value for value in realized_bps if value is not None]
        trade_count = len(realized_bps)
        if not realized_bps and fills:
            realized_bps = [
                -(
                    float((row.get("payload") or {}).get("fee", 0.0) or 0.0)
                    + float((row.get("payload") or {}).get("slippage_cost", 0.0) or 0.0)
                )
                for row in fills[-window:]
            ]
            trade_count = len(realized_bps)
        net_expectancy_bps = 0.0 if not realized_bps else sum(realized_bps) / len(realized_bps)
        wins = [value for value in realized_bps if value > 0.0]
        losses = [value for value in realized_bps if value <= 0.0]
        win_rate = 0.0 if not realized_bps else len(wins) / len(realized_bps)
        avg_win_bps = 0.0 if not wins else sum(wins) / len(wins)
        avg_loss_bps = 0.0 if not losses else sum(losses) / len(losses)
        avg_hold_minutes = 0.0
        hold_minutes = []
        for row in trade_rows:
            for key in ("hold_minutes", "hold_time_minutes"):
                value = row.get(key)
                if value is None:
                    continue
                try:
                    hold_minutes.append(float(value))
                except Exception:
                    pass
        if hold_minutes:
            avg_hold_minutes = sum(hold_minutes) / len(hold_minutes)
        orders_submitted = sum(1 for row in order_events if str(row.get("event_type", "")).upper() == "ORDER_INTENT")
        fill_rate = 0.0 if orders_submitted <= 0 else len(fills) / max(orders_submitted, 1)
        maker_count = sum(
            1
            for row in order_events
            if "limit" in str((row.get("payload") or {}).get("metadata", {}).get("execution_style", "")).lower()
            or "limit" in str((row.get("payload") or {}).get("order_style", "")).lower()
        )
        maker_ratio = 0.0 if orders_submitted <= 0 else maker_count / max(orders_submitted, 1)
        false_negative_rate = 0.0
        false_positive_rate = 0.0
        if ranked_candidates:
            false_positive_rate = sum(1 for row in ranked_candidates if float(row.get("expected_net_edge_bps", 0.0) or 0.0) <= 0.0) / max(len(ranked_candidates), 1)
            false_negative_rate = sum(1 for row in ranked_candidates if not bool(row.get("admission_allowed", True)) and float(row.get("expected_net_edge_bps", 0.0) or 0.0) > 0.0) / max(len(ranked_candidates), 1)
        hold_time_adjusted_expectancy = net_expectancy_bps if avg_hold_minutes <= 0.0 else net_expectancy_bps * min(1.5, 60.0 / max(avg_hold_minutes, 5.0))
        capital_efficiency_expectancy = net_expectancy_bps * max(fill_rate, 0.10)
        sample_guard = trade_count >= int(self.settings.expectancy.min_sample_guard)
        promotion_score = max(
            0.0,
            min(
                1.0,
                net_expectancy_bps / max(float(self.settings.expectancy.promotion_expectancy_bps), 1.0) * 0.45
                + fill_rate * 0.20
                + maker_ratio * 0.15
                + min(trade_count / max(int(self.settings.expectancy.min_sample_guard), 1), 1.0) * 0.20,
            ),
        )
        report = ExpectancyEngineReport(
            ts=datetime.now(timezone.utc),
            trade_count=trade_count,
            net_expectancy_bps=net_expectancy_bps,
            capital_efficiency_expectancy=capital_efficiency_expectancy,
            hold_time_adjusted_expectancy=hold_time_adjusted_expectancy,
            win_rate=win_rate,
            avg_win_bps=avg_win_bps,
            avg_loss_bps=avg_loss_bps,
            avg_hold_minutes=avg_hold_minutes,
            false_negative_rate=false_negative_rate,
            false_positive_rate=false_positive_rate,
            promotion_score=promotion_score,
            promotion_ready=sample_guard and promotion_score >= float(self.settings.experiments.promotion_score_min),
            metadata={
                "fill_rate": fill_rate,
                "maker_ratio": maker_ratio,
                "round_trips_per_day": trade_count / 30.0,
                "confidence_calibration": max(0.0, min(1.0, win_rate - false_positive_rate * 0.5)),
                "sample_guard": sample_guard,
            },
        )
        payload = asdict(report)
        intraday_buckets = {bucket: net_expectancy_bps for bucket in self.settings.expectancy.intraday_session_buckets}
        return {
            "report": payload,
            "expectancy_engine_report": payload,
            "expectancy_segment_matrix": {
                "ts": payload["ts"],
                "per_pair": {},
                "per_playbook": {},
                "per_regime": {},
                "per_execution_style": {},
            },
            "playbook_promotion_readiness": {
                "ts": payload["ts"],
                "promotion_ready": payload["promotion_ready"],
                "min_sample_guard": int(self.settings.expectancy.min_sample_guard),
                "trade_count": trade_count,
            },
            "pair_regime_expectancy_grid": {
                "ts": payload["ts"],
                "grid": {},
            },
            "promotion_score_report": {
                "ts": payload["ts"],
                "promotion_score": promotion_score,
                "promotion_ready": payload["promotion_ready"],
            },
            "intraday_session_model_report": {
                "ts": payload["ts"],
                "sessions": intraday_buckets,
            },
            "meta_router_report": {
                "ts": payload["ts"],
                "best_playbook": None if not ranked_candidates else ranked_candidates[0].get("playbook"),
                "candidate_count": len(ranked_candidates),
            },
            "confidence_calibration_report": {
                "ts": payload["ts"],
                "confidence_calibration": payload["metadata"]["confidence_calibration"],
                "win_rate": win_rate,
                "false_positive_rate": false_positive_rate,
            },
        }

