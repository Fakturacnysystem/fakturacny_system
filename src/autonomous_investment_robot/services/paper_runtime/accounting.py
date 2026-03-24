from __future__ import annotations

from dataclasses import asdict
from typing import Any

from autonomous_investment_robot.services.replay.events import PositionEvent, RiskEvent, make_event


class PaperAccountingCoordinator:
    def __init__(
        self,
        *,
        recon: Any,
        risk: Any,
        execution: Any,
        event_store: Any,
        observability: Any,
        ops: Any,
        policy: Any,
        incidents: Any,
        notifier: Any,
        mlops: Any,
        replay: Any,
    ) -> None:
        self.recon = recon
        self.risk = risk
        self.execution = execution
        self.event_store = event_store
        self.observability = observability
        self.ops = ops
        self.policy = policy
        self.incidents = incidents
        self.notifier = notifier
        self.mlops = mlops
        self.replay = replay

    def finalize_run(
        self,
        *,
        symbol: str,
        equity: float,
        peak: float,
        exposure: float,
        funding_paid_pct: float,
        fills_all: list[Any],
        plans: list[dict[str, Any]],
        trade_log: list[dict[str, Any]],
        fvs: list[Any],
    ) -> dict[str, Any]:
        rec_report = self.recon.reconcile_report(
            fills=fills_all,
            internal_exposure=exposure,
            open_orders_state_ok=True,
            cash_ok=True,
        )
        rec_ok, rec_reason = rec_report.ok, rec_report.code
        if not rec_ok:
            self.risk.state.kill_switch = True
            self.risk.state.safe_mode = True
            self.event_store.append(
                "risk",
                make_event(
                    RiskEvent,
                    "RECONCILIATION_MISMATCH",
                    symbol,
                    "paper",
                    self.event_store.next_seq("risk"),
                    {
                        "reason": rec_reason,
                        "severity": rec_report.severity.value,
                        "action": rec_report.action.value,
                        "details": rec_report.details,
                    },
                ),
            )
            self.observability.journal("reconciliation_journal", rec_report)
            fills_all.append(self.execution.flatten_worst_case(symbol, exposure))
            exposure = 0.0
        else:
            self.observability.journal("reconciliation_journal", rec_report)

        drawdown_signed = (equity / peak - 1) * 100
        drawdown = max(0.0, (1.0 - (equity / peak)) * 100)
        psi = self.mlops.detector.psi([x.values["ret_1"] for x in fvs[: max(1, len(fvs)//2)]], [x.values["ret_1"] for x in fvs[max(1, len(fvs)//2):]])
        if self.mlops.should_rollback(drawdown, psi):
            self.event_store.append("risk", make_event(RiskEvent, "AUTO_ROLLBACK", symbol, "paper", self.event_store.next_seq("risk"), {"drawdown_pct": drawdown, "drawdown_signed_pct": drawdown_signed, "psi": psi}))

        self.event_store.append("positions", make_event(PositionEvent, "POSITION_SNAPSHOT", symbol, "paper", self.event_store.next_seq("positions"), {"exposure_notional": exposure}))

        self.ops.set_metric("data_lag_seconds", 0.0)
        self.ops.set_metric("pnl", (equity - 1.0) * 100)
        self.ops.set_metric("drawdown", drawdown)
        self.ops.set_metric("exposure_notional", abs(exposure))
        self.ops.set_metric("kill_switch_state", 1.0 if self.risk.state.kill_switch else 0.0)
        self.ops.set_metric("compliance_veto_state", 0.0)
        self.ops.set_metric("reconciliation_mismatch_total", 0.0 if rec_ok else 1.0)
        self.ops.set_metric("slippage_bps", getattr(self.execution.settings, "slippage_bps", 0.0))
        self.ops.set_metric("fees_paid", sum(f.fee for f in fills_all))
        self.ops.set_metric("funding_paid", funding_paid_pct)
        maker_count = len([f for f in fills_all if "maker" in f.status])
        self.ops.set_metric("maker_fill_rate", 0.0 if not fills_all else maker_count / len(fills_all))
        avg_cost = 0.0
        if trade_log:
            vals = []
            for trade in trade_log:
                comps = trade.get("why", {}).get("components", [])
                vals.extend([component.get("cost_total_bps", 0.0) for component in comps])
            if vals:
                avg_cost = sum(vals) / len(vals)

        self.ops.set_metric("cost_total_bps", avg_cost)
        self.ops.set_metric("crowding_score", getattr(self.risk.state, "last_crowding_score", 0.0))
        self.ops.set_metric("funding_budget_utilization", getattr(self.risk.state, "funding_budget_utilization", 0.0))
        for key, value in self.policy.allocator.state.weights.items():
            self.ops.set_metric(f"allocator_weight_{key}", value)

        inc = self.incidents.evaluate(self.ops.metrics)
        if inc is not None:
            self.notifier.notify(inc.action, inc.reason)

        self.ops.export_prometheus()
        checksums = self.replay.persist_outputs(
            equity=equity,
            drawdown=drawdown,
            drawdown_signed=drawdown_signed,
            funding_paid_pct=funding_paid_pct,
            fills_all=fills_all,
            plans=plans,
            trade_log=trade_log,
        )
        return {"status": "ok", "orders": len(plans), "fills": len(fills_all), **checksums}
