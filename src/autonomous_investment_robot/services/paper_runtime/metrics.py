from __future__ import annotations

from typing import Any

from autonomous_investment_robot.config.settings import UNSPECIFIED


class MetricsCoordinator:
    def __init__(self, *, ops: Any, risk: Any, settings: Any) -> None:
        self.ops = ops
        self.risk = risk
        self.settings = settings

    def update_risk_metrics(self, *, decision: Any, oi_spike: float, liquidations: float) -> None:
        self.ops.set_metric("crowding_score", getattr(self.risk.state, "last_crowding_score", 0.0))
        crowd_level = getattr(self.risk.state, "last_crowding_level", "none")
        crowd_map = {"none": 0.0, "low": 1.0, "medium": 2.0, "high": 3.0, "extreme": 4.0}
        self.ops.set_metric("crowding_level", crowd_map.get(crowd_level, 0.0))
        self.ops.set_metric("funding_budget_utilization", getattr(self.risk.state, "funding_budget_utilization", 0.0))
        self.ops.set_metric("risk_mode", float({"normal": 0, "cautious": 1, "degraded": 2, "defensive": 3, "flatten-only": 4, "kill-switch": 5}.get(self.risk.state.risk_mode, 0.0)))
        self.ops.set_metric("liquidation_spike", liquidations)
        self.ops.set_metric("oi_spike_pct", oi_spike)
        self.ops.set_metric("max_liquidation_spike", float(self.settings.risk.max_liquidation_spike))
        self.ops.set_metric("max_oi_spike_pct", float(self.settings.risk.max_oi_spike_pct))
        self.ops.set_metric(
            "crowding_score_extreme",
            float(
                getattr(self.settings.risk, "crowding_score_extreme", self.settings.risk.crowding_score_kill)
                if getattr(self.settings.risk, "crowding_score_extreme", "UNSPECIFIED") != UNSPECIFIED
                else self.settings.risk.crowding_score_kill
            ),
        )
        if decision.reason in {"crowding_radar_kill", "crowding_high_block_open_reduce_only", "funding_cost_limit", "funding_budget_throttle_block_open"}:
            self.ops.audit_event(
                "risk_guard",
                {
                    "reason": decision.reason,
                    "details": decision.details,
                },
            )
