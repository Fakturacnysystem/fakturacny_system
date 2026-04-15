from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import FillAwareCostReport


class FillAwareCostModelService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def analyze(
        self,
        *,
        market: Any,
        execution_plan: Any | None,
        execution_quality: Any | None,
        execution_result: Any | None,
    ) -> dict[str, Any]:
        book = dict(getattr(market, "book", {}) or {})
        spread_bps = float(book.get("spread_bps", 0.0) or 0.0)
        bid = float(book.get("bid", 0.0) or 0.0)
        ask = float(book.get("ask", 0.0) or 0.0)
        mid = (bid + ask) / 2.0 if bid > 0.0 and ask > 0.0 else max(bid, ask, 0.0)
        passive_preferred = bool(getattr(execution_quality, "passive_preferred", False)) if execution_quality is not None else bool(self.settings.execution.maker_preference)
        maker_probability = 0.80 if passive_preferred else 0.35
        taker_probability = max(0.0, 1.0 - maker_probability)
        price_quality_bps = 0.0 if execution_quality is None else float(getattr(execution_quality, "expected_price_quality_bps", 0.0) or 0.0)
        adverse_selection = 0.0 if execution_quality is None else float(getattr(execution_quality, "adverse_selection_risk", 0.0) or 0.0) * 20.0
        slippage_bps = float(self.settings.execution.slippage_bps) + price_quality_bps * taker_probability
        fill_probability = 0.0 if execution_quality is None else float(getattr(execution_quality, "fill_probability", 0.0) or 0.0)
        cancel_to_fill_ratio = 0.0 if fill_probability <= 0.0 else max(0.0, 1.0 / max(fill_probability, 0.01) - 1.0)
        post_only_reject_burden = 0.25 if passive_preferred and execution_result is not None and "reject" in str(getattr(execution_result, "status", "")).lower() else 0.0
        repricing_burden = 0.10 if execution_plan is not None and str(getattr(execution_plan, "order_style", "")) == "limit" else 0.0
        partial_fill_burden = max(0.0, 1.0 - fill_probability) * 0.35
        degradation = 1.0 if execution_result is not None and str(getattr(execution_result, "status", "")).lower() in {"rejected", "error"} else 0.0
        expected_fill_price = mid * (1.0 + ((slippage_bps + adverse_selection) / 10000.0))
        total_cost_bps = float(self.settings.execution.fee_bps) + slippage_bps + adverse_selection + post_only_reject_burden * 10.0
        report = FillAwareCostReport(
            ts=datetime.now(timezone.utc),
            maker_probability=maker_probability,
            taker_probability=taker_probability,
            expected_fill_price=expected_fill_price,
            spread_capture_probability=max(0.0, min(1.0, maker_probability - spread_bps / 100.0)),
            slippage_bps=slippage_bps,
            adverse_selection_bps=adverse_selection,
            cancel_to_fill_ratio=cancel_to_fill_ratio,
            post_only_reject_burden=post_only_reject_burden,
            repricing_burden=repricing_burden,
            partial_fill_burden=partial_fill_burden,
            live_degradation_delta=degradation,
            total_cost_bps=total_cost_bps,
            metadata={
                "mid_price": mid,
                "spread_bps": spread_bps,
                "fill_probability": fill_probability,
            },
        )
        payload = asdict(report)
        return {
            "cost_model_diagnostics": payload,
            "fill_quality_report": {
                "ts": payload["ts"],
                "fill_probability": fill_probability,
                "spread_capture_probability": payload["spread_capture_probability"],
                "expected_price_quality_bps": price_quality_bps,
            },
            "maker_taker_mix_report": {
                "ts": payload["ts"],
                "maker_probability": maker_probability,
                "taker_probability": taker_probability,
            },
            "cancel_replace_efficiency": {
                "ts": payload["ts"],
                "cancel_to_fill_ratio": cancel_to_fill_ratio,
                "repricing_burden": repricing_burden,
                "post_only_reject_burden": post_only_reject_burden,
            },
            "cost_sensitivity_analysis": {
                "ts": payload["ts"],
                "base_total_cost_bps": total_cost_bps,
                "stress_bands": {
                    "base": total_cost_bps,
                    "moderate": total_cost_bps * 1.25,
                    "stress": total_cost_bps * 1.50,
                },
            },
            "live_degradation_delta_report": {
                "ts": payload["ts"],
                "live_degradation_delta": degradation,
                "status": None if execution_result is None else str(getattr(execution_result, "status", "")),
            },
        }

