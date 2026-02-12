from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.compliance.service import ComplianceService
from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.event_store.service import EventStore
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.feature_store.service import FeatureStoreService
from autonomous_investment_robot.services.models.service import ModelsService
from autonomous_investment_robot.services.oms.service import ManagedOrder, OMSService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.policy.service import OrderIntent, PolicyService
from autonomous_investment_robot.services.raw_store.service import RawStoreService
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService
from autonomous_investment_robot.services.replay.events import (
    ComplianceEvent,
    FillEvent,
    OrderEvent,
    OrderIntentEvent,
    PositionEvent,
    RiskEvent,
    make_event,
    make_idempotency_key,
)
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


class RobotOrchestrator:
    def __init__(self, settings: RobotSettings) -> None:
        self.settings = settings
        self.ingestion = DataIngestionService()
        self.raw = RawStoreService(settings.storage.run_dir)
        self.event_store = EventStore(settings.storage.run_dir)
        self.features = FeatureStoreService()
        self.models = ModelsService()
        self.policy = PolicyService(settings.policy)
        self.risk = RiskEngineService(settings.risk, safe_mode=settings.safe_mode_default)
        self.execution = ExecutionService(settings.execution)
        self.recon = ReconciliationService()
        self.compliance = ComplianceService(settings.provider_whitelist)
        self.oms = OMSService()
        self.ops = OpsService(settings.storage.run_dir)

    def boot(self) -> dict:
        self.ops.track_config(asdict(self.settings))
        symbol = self.settings.universe[0]
        provider = "paper_sim_provider"
        c = self.compliance.check_provider_authorization(provider)
        self.event_store.append(
            "compliance",
            make_event(
                ComplianceEvent,
                "COMPLIANCE_CHECK",
                symbol=symbol,
                venue=provider,
                seq=self.event_store.next_seq("compliance"),
                payload={"allowed": c.allowed, "reason": c.reason},
            ),
        )
        self.ops.set_metric("compliance_veto_state", 0.0 if c.allowed else 1.0)
        if not c.allowed:
            self.ops.emit_alert("compliance_veto", c.reason)
            return {"status": "blocked", "reason": c.reason}

        bars = self.ingestion.replay_csv(symbol, self.settings.fixtures.ohlcv_csv)
        fvs = self.features.build_from_bars(bars)

        equity, peak, exposure = 1.0, 1.0, 0.0
        fills_all, plans = [], []

        for i in range(1, len(fvs)):
            fv = fvs[i - 1]
            self.features.assert_no_leakage(fv.ts, bars[i].ts)
            fc = self.models.forecast(fv)
            intent = self.policy.make_intent(fc)
            if intent is None:
                self.ops.inc_metric("orders_rejected_total")
                continue

            risk = self.risk.evaluate(
                intent,
                current_exposure=abs(exposure),
                drawdown_pct=(equity / peak - 1) * 100,
                daily_loss_pct=min(0.0, (equity - 1.0) * 100),
                data_lag_seconds=0.0,
                spread_bps=float(fv.values["spread_proxy"] * 10000),
                depth_notional=100000.0,
                reconciliation_ok=True,
            )
            if not risk.allowed:
                self.event_store.append(
                    "risk",
                    make_event(
                        RiskEvent,
                        "RISK_REJECT",
                        symbol=symbol,
                        venue="paper",
                        seq=self.event_store.next_seq("risk"),
                        payload={"reason": risk.reason},
                    ),
                )
                self.ops.inc_metric("orders_rejected_total")
                if self.risk.state.kill_switch:
                    break
                continue

            adjusted_intent = OrderIntent(symbol=intent.symbol, side=intent.side, target_notional=risk.adjusted_notional, why=intent.why)
            idem = make_idempotency_key(asdict(adjusted_intent), run_id="paper-run", sequence=i)
            order_id = f"ord-{i}"
            self.event_store.append(
                "orders",
                make_event(
                    OrderIntentEvent,
                    "ORDER_INTENT",
                    symbol=symbol,
                    venue="paper",
                    seq=self.event_store.next_seq("orders"),
                    payload=asdict(adjusted_intent),
                    idempotency_key=idem,
                ),
            )

            ok, _ = self.oms.submit_intent(
                ManagedOrder(order_id=order_id, symbol=symbol, side=adjusted_intent.side, notional=adjusted_intent.target_notional, idempotency_key=idem)
            )
            if not ok:
                self.ops.inc_metric("orders_rejected_total")
                continue
            self.oms.transition(order_id, "ACK")
            self.event_store.append(
                "orders",
                make_event(
                    OrderEvent,
                    "ORDER_ACK",
                    symbol=symbol,
                    venue="paper",
                    seq=self.event_store.next_seq("orders"),
                    payload={"order_id": order_id, "state": "ACK"},
                    idempotency_key=idem,
                ),
            )

            fills = self.execution.execute_paper(order_id=order_id, intent=adjusted_intent, mid_price=bars[i].close)
            for fill in fills:
                self.oms.apply_fill(order_id, fill.notional)
                self.event_store.append(
                    "fills",
                    make_event(
                        FillEvent,
                        "FILL",
                        symbol=symbol,
                        venue="paper",
                        seq=self.event_store.next_seq("fills"),
                        payload=asdict(fill),
                        idempotency_key=fill.fill_id,
                    ),
                )
                fills_all.append(fill)

            fill_notional = sum(f.notional for f in fills)
            fees = sum(f.fee + f.slippage_cost for f in fills)
            side = 1 if adjusted_intent.side == "buy" else -1
            ret = side * (bars[i].close / bars[i - 1].close - 1)
            pnl = fill_notional * ret - fees
            self.risk.record_return((pnl / max(adjusted_intent.target_notional, 1.0)) * 100)
            equity += pnl / max(self.settings.policy.base_risk_budget, 1.0)
            peak = max(peak, equity)
            exposure += fill_notional if adjusted_intent.side == "buy" else -fill_notional
            plans.append({"order_id": order_id, **asdict(adjusted_intent)})
            self.ops.inc_metric("orders_submitted_total")

        rec_ok, rec_reason = self.recon.reconcile(fills_all, internal_exposure=exposure, open_orders_state_ok=True, cash_ok=True)
        if not rec_ok:
            self.risk.state.safe_mode = True
            self.risk.state.kill_switch = True
            self.event_store.append(
                "risk",
                make_event(
                    RiskEvent,
                    "RECONCILIATION_MISMATCH",
                    symbol=symbol,
                    venue="paper",
                    seq=self.event_store.next_seq("risk"),
                    payload={"reason": rec_reason},
                ),
            )
            flatten_fill = self.execution.flatten_worst_case(symbol=symbol, exposure_notional=exposure)
            fills_all.append(flatten_fill)
            exposure = 0.0

        self.event_store.append(
            "positions",
            make_event(
                PositionEvent,
                "POSITION_SNAPSHOT",
                symbol=symbol,
                venue="paper",
                seq=self.event_store.next_seq("positions"),
                payload={"exposure_notional": exposure},
            ),
        )

        drawdown = (equity / peak - 1) * 100
        self.ops.set_metric("data_lag_seconds", 0.0)
        self.ops.set_metric("pnl", (equity - 1.0) * 100)
        self.ops.set_metric("drawdown", drawdown)
        self.ops.set_metric("exposure_notional", abs(exposure))
        self.ops.set_metric("kill_switch_state", 1.0 if self.risk.state.kill_switch else 0.0)
        self.ops.set_metric("reconciliation_mismatch_total", 0.0 if rec_ok else 1.0)
        self.ops.set_metric("slippage_bps", self.settings.execution.slippage_bps)
        self.ops.set_metric("fees_paid", sum(f.fee for f in fills_all))
        self.ops.set_metric("funding_paid", 0.0)
        self.ops.export_prometheus()

        self.raw.write_table("order_plans", plans)
        self.raw.write_table("fills", [asdict(f) for f in fills_all])
        self.raw.write_table("report", [{"equity": equity, "drawdown": drawdown}])

        checksums = {
            "orders_checksum": sha256(json.dumps(plans, sort_keys=True, default=str).encode()).hexdigest(),
            "fills_checksum": sha256(json.dumps([asdict(f) for f in fills_all], sort_keys=True, default=str).encode()).hexdigest(),
            "equity_checksum": sha256(json.dumps({"equity": equity, "drawdown": drawdown}, sort_keys=True).encode()).hexdigest(),
        }
        self.raw.write_table("checksums", [checksums])
        return {"status": "ok", "orders": len(plans), "fills": len(fills_all), **checksums}
