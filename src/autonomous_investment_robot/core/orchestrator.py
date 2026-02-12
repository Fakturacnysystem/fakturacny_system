from __future__ import annotations

from dataclasses import asdict

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.compliance.service import ComplianceService
from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.data_qa.service import DataQAService
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.feature_store.service import FeatureStoreService
from autonomous_investment_robot.services.models.service import ModelsService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.policy.service import PolicyService
from autonomous_investment_robot.services.raw_store.service import RawStoreService
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


class RobotOrchestrator:
    def __init__(self, settings: RobotSettings) -> None:
        self.settings = settings
        self.ingestion = DataIngestionService()
        self.qa = DataQAService()
        self.raw = RawStoreService(settings.storage.run_dir)
        self.features = FeatureStoreService()
        self.models = ModelsService()
        self.policy = PolicyService(settings.policy)
        self.risk = RiskEngineService(settings.risk, safe_mode=settings.safe_mode_default)
        self.execution = ExecutionService(settings.execution)
        self.recon = ReconciliationService()
        self.compliance = ComplianceService(settings.provider_whitelist)
        self.ops = OpsService(settings.storage.run_dir)

    def boot(self) -> dict:
        symbol = self.settings.universe[0]
        provider = "paper_sim_provider"
        c = self.compliance.check_provider_authorization(provider)
        self.ops.set_metric("compliance_veto_state", 0.0 if c.allowed else 1.0)
        if not c.allowed:
            self.ops.emit_alert("compliance_veto", c.reason)
            return {"status": "blocked", "reason": c.reason}

        bars = self.ingestion.replay_csv(symbol, self.settings.fixtures.ohlcv_csv)
        ok, issues = self.qa.validate_replay(bars)
        data_lag = 0.0
        self.ops.set_metric("data_lag_seconds", data_lag)
        if not ok:
            self.ops.set_metric("kill_switch_state", 1.0)
            return {"status": "blocked", "reason": ",".join(issues)}
        self.raw.write_table("raw_bars", [asdict(b) for b in bars])

        fvs = self.features.build_from_bars(bars)
        self.raw.write_table("features", [asdict(fv) for fv in fvs])

        equity = 1.0
        peak = 1.0
        exposure = 0.0
        daily_loss_pct = 0.0
        plans, fills_rows, forecast_rows = [], [], []

        for i in range(1, len(fvs)):
            fv = fvs[i - 1]
            self.features.assert_no_leakage(fv.ts, bars[i].ts)
            fc = self.models.forecast(fv)
            forecast_rows.append(asdict(fc))
            intent = self.policy.make_intent(fc)
            if intent is None:
                self.ops.inc_metric("orders_rejected")
                continue

            risk_decision = self.risk.evaluate(
                intent=intent,
                current_exposure=exposure,
                drawdown_pct=(equity / peak - 1) * 100,
                daily_loss_pct=daily_loss_pct,
                data_stale=False,
                reconciliation_ok=True,
            )
            if not risk_decision.allowed:
                self.ops.inc_metric("orders_rejected")
                self.ops.audit_event("risk_reject", {"reason": risk_decision.reason})
                continue

            plans.append(asdict(intent))
            fills = self.execution.execute_paper(intent, mid_price=bars[i].close)
            fill_notional = sum(f.notional for f in fills)
            fees = sum(f.fee + f.slippage_cost for f in fills)
            side = 1 if intent.side == "buy" else -1
            pnl = side * fill_notional * (bars[i].close / bars[i - 1].close - 1) - fees
            equity += pnl / max(self.settings.policy.base_risk_budget, 1.0)
            peak = max(peak, equity)
            exposure += fill_notional
            daily_loss_pct = min(0.0, (equity - 1.0) * 100)

            rec_ok, rec_reason = self.recon.reconcile(fills, expected_notional=fill_notional)
            if not rec_ok:
                self.ops.set_metric("kill_switch_state", 1.0)
                self.ops.emit_alert("reconciliation_mismatch", rec_reason)
                break

            self.ops.inc_metric("orders_submitted")
            for f in fills:
                fills_rows.append(asdict(f))

        drawdown_pct = (equity / peak - 1) * 100
        self.ops.set_metric("pnl", (equity - 1.0) * 100)
        self.ops.set_metric("drawdown", drawdown_pct)
        self.ops.set_metric("exposure_notional", exposure)
        self.ops.set_metric("kill_switch_state", 1.0 if self.risk.state.kill_switch else 0.0)
        self.ops.export_prometheus()

        self.raw.write_table("forecasts", forecast_rows)
        self.raw.write_table("order_plans", plans)
        self.raw.write_table("fills", fills_rows)
        self.raw.write_table("positions", [{"symbol": symbol, "exposure_notional": exposure}])
        self.raw.write_table("risk_events", [{"kill_switch": self.risk.state.kill_switch}])
        self.raw.write_table(
            "report",
            [{"equity": equity, "drawdown_pct": drawdown_pct, "orders": len(plans), "fills": len(fills_rows)}],
        )
        return {"status": "ok", "orders": len(plans), "fills": len(fills_rows), "run_dir": self.settings.storage.run_dir}
