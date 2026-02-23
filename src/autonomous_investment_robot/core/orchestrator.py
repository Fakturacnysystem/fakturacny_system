from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings, UNSPECIFIED
from autonomous_investment_robot.connectors.cex.binance_um_perps import BinanceUMPerpsConnector
from autonomous_investment_robot.connectors.cex.kraken_derivatives import KrakenDerivativesConnector
from autonomous_investment_robot.services.compliance.service import ComplianceService
from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.data_qa.service import DataQAService
from autonomous_investment_robot.services.event_store.service import EventStore
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.execution.live_binance_service import LiveBinanceService
from autonomous_investment_robot.services.execution.live_kraken_service import LiveKrakenService
from autonomous_investment_robot.services.feature_store.service import FeatureStoreService
from autonomous_investment_robot.services.incident.service import IncidentPolicy, Notifier
from autonomous_investment_robot.services.mlops.service import MLOpsService
from autonomous_investment_robot.services.models.service import ModelsService
from autonomous_investment_robot.services.oms.service import ManagedOrder, OMSService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.policy.service import OrderIntent, PolicyService
from autonomous_investment_robot.services.raw_store.service import RawStoreService
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService
from autonomous_investment_robot.services.replay.events import ComplianceEvent, FillEvent, OrderEvent, OrderIntentEvent, PositionEvent, RiskEvent, make_event, make_idempotency_key
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


class RobotOrchestrator:
    def __init__(self, settings: RobotSettings) -> None:
        self.settings = settings
        self.ingestion = DataIngestionService()
        self.qa = DataQAService()
        self.raw = RawStoreService(settings.storage.run_dir)
        self.event_store = EventStore(settings.storage.run_dir)
        self.features = FeatureStoreService()
        self.models = ModelsService(regime_settings=settings.regime)
        self.policy = PolicyService(settings.policy, settings.allocator, settings.tco)
        self.risk = RiskEngineService(settings.risk, safe_mode=settings.safe_mode_default)
        self.execution = ExecutionService(settings.execution)
        self.recon = ReconciliationService()
        self.compliance = ComplianceService(settings.provider_whitelist)
        self.oms = OMSService()
        self.ops = OpsService(settings.storage.run_dir)
        self.incidents = IncidentPolicy()
        self.notifier = Notifier()
        self.mlops = MLOpsService(settings.mlops.rollback_dd_threshold_pct, settings.mlops.drift_psi_threshold)

    def _missing_limits(self) -> bool:
        req = [
            self.settings.risk.max_daily_loss_pct,
            self.settings.risk.max_drawdown_pct,
            self.settings.risk.max_position_notional,
            self.settings.risk.max_exposure_notional,
            self.settings.risk.max_orders_per_min,
            self.settings.risk.leverage,
            self.settings.risk.max_spread_bps,
            self.settings.risk.min_depth_notional,
            self.settings.risk.stale_data_seconds,
            self.settings.risk.min_margin_buffer,
            self.settings.risk.max_funding_cost_per_day,
            self.settings.risk.max_oi_spike_pct,
            self.settings.risk.max_liquidation_spike,
            self.settings.risk.divergence_threshold_bps,
            self.settings.risk.crowding_score_kill,
            self.settings.tco.max_total_cost_bps,
            self.settings.tco.max_impact_bps,
        ]
        return any(v == UNSPECIFIED for v in req)

    def boot(self) -> dict:
        self.ops.track_config(asdict(self.settings))
        symbol = self.settings.universe[0]
        mode = self.settings.execution_mode_enum()
        provider = "paper_sim_provider" if mode == ExecutionMode.PAPER else self.settings.execution.provider_id
        c = self.compliance.check_provider_authorization(provider)
        self.event_store.append("compliance", make_event(ComplianceEvent, "COMPLIANCE_CHECK", symbol, provider, self.event_store.next_seq("compliance"), {"allowed": c.allowed, "reason": c.reason}))
        if not c.allowed:
            return {"status": "blocked", "reason": c.reason}
        if self._missing_limits():
            return {"status": "blocked", "reason": "missing_required_limits"}

        if mode != ExecutionMode.PAPER:
            if self.settings.execution.provider_id == "kraken_derivatives":
                live = LiveKrakenService(
                    settings=self.settings,
                    run_id=self.settings.storage.run_dir.replace("/", "_"),
                    connector=KrakenDerivativesConnector(self.settings.execution.kraken),
                )
            else:
                live = LiveBinanceService(
                    settings=self.settings,
                    run_id=self.settings.storage.run_dir.replace("/", "_"),
                    connector=BinanceUMPerpsConnector(self.settings.execution.binance),
                )
            self.execution.attach_live_service(live)
            ok_preflight, reason_preflight = live.preflight()
            self.recon.persist_report(
                self.settings.storage.run_dir,
                {"mode": mode.value, "preflight_ok": ok_preflight, "reason": reason_preflight},
            )
            if not ok_preflight:
                self.ops.inc_metric("auth_errors_total")
                inc = self.incidents.evaluate(self.ops.metrics)
                if inc is not None:
                    self.notifier.notify(inc.action, inc.reason)
                return {"status": "blocked", "reason": reason_preflight}
            return {"status": "ok", "mode": mode.value, "reason": "live_preflight_passed"}

        if len(self.settings.universe) > 1:
            if not self.settings.fixtures.symbol_files:
                return {"status": "blocked", "reason": "missing_symbol_fixtures"}
            for sym in self.settings.universe:
                if sym not in self.settings.fixtures.symbol_files:
                    return {"status": "blocked", "reason": f"missing_fixture_for_{sym}"}

        bars = self.ingestion.replay_csv(symbol, self.settings.fixtures.ohlcv_csv)
        ok, issues = self.qa.validate_replay(bars)
        if not ok:
            return {"status": "blocked", "reason": ",".join(issues)}

        fvs = self.features.build_from_bars(bars)

        equity, peak, exposure = 1.0, 1.0, 0.0
        funding_paid_pct = 0.0
        strategy_perf = {s.name: 0.0 for s in self.policy.strategies}
        fills_all, plans, trade_log = [], [], []

        for i in range(1, len(fvs)):
            fv = fvs[i - 1]
            bar = bars[i]
            self.features.assert_no_leakage(fv.ts, bar.ts)

            if self.qa.divergence_breaker(bar, float(self.settings.risk.divergence_threshold_bps)):
                self.risk.state.kill_switch = True
                self.risk.state.safe_mode = True
                self.event_store.append("risk", make_event(RiskEvent, "DIVERGENCE_KILL", symbol, "paper", self.event_store.next_seq("risk"), {"divergence": True}))
                if abs(exposure) > 0:
                    fills_all.append(self.execution.flatten_worst_case(symbol, exposure))
                    exposure = 0.0
                break

            fc = self.models.forecast(fv)
            intent = self.policy.make_intent(fc, fv.values, self.settings.execution.fee_bps, self.settings.execution.slippage_bps)
            if intent is None:
                self.ops.inc_metric("orders_rejected_total")
                if self.policy.last_veto_reasons:
                    self.ops.inc_metric("veto_tco_total", float(len(self.policy.last_veto_reasons)))
                    for reason, count in self.policy.last_veto_counts.items():
                        self.ops.inc_metric(f"veto_{reason}_total", float(count))
                continue

            oi_prev = max(1.0, bars[i - 1].oi)
            oi_spike = (bar.oi - oi_prev) / oi_prev * 100
            divergence_bps = abs(bar.mark_price - bar.secondary_price) / max(bar.mark_price, 1e-9) * 10000
            margin_buffer = 2.5

            decision = self.risk.evaluate(
                intent,
                current_exposure=abs(exposure),
                drawdown_pct=(equity / peak - 1) * 100,
                daily_loss_pct=min(0.0, (equity - 1.0) * 100),
                data_lag_seconds=0.0,
                spread_bps=bar.spread_bps,
                depth_notional=bar.depth_notional,
                reconciliation_ok=True,
                funding_paid_pct=funding_paid_pct,
                oi_spike_pct=oi_spike,
                liquidation_spike=bar.liquidations,
                divergence_bps=divergence_bps,
                margin_buffer=margin_buffer,
                funding_rate_abs=abs(bar.funding_rate),
                market_regime=fc.regime,
                liquidity_regime=fc.liquidity_regime,
            )
            self.ops.set_metric("crowding_score", getattr(self.risk.state, "last_crowding_score", 0.0))
            crowd_level = getattr(self.risk.state, "last_crowding_level", "none")
            crowd_map = {"none": 0.0, "low": 1.0, "medium": 2.0, "high": 3.0, "extreme": 4.0}
            self.ops.set_metric("crowding_level", crowd_map.get(crowd_level, 0.0))
            self.ops.set_metric("funding_budget_utilization", getattr(self.risk.state, "funding_budget_utilization", 0.0))
            self.ops.set_metric("liquidation_spike", bar.liquidations)
            self.ops.set_metric("oi_spike_pct", oi_spike)
            self.ops.set_metric("max_liquidation_spike", float(self.settings.risk.max_liquidation_spike))
            self.ops.set_metric("max_oi_spike_pct", float(self.settings.risk.max_oi_spike_pct))
            self.ops.set_metric("crowding_score_extreme", float(getattr(self.settings.risk, "crowding_score_extreme", self.settings.risk.crowding_score_kill) if getattr(self.settings.risk, "crowding_score_extreme", "UNSPECIFIED") != UNSPECIFIED else self.settings.risk.crowding_score_kill))
            if decision.reason in {"crowding_radar_kill", "crowding_high_block_open_reduce_only", "funding_cost_limit", "funding_budget_throttle_block_open"}:
                self.ops.audit_event(
                    "risk_guard",
                    {
                        "reason": decision.reason,
                        "details": decision.details,
                        "symbol": symbol,
                        "bar_ts": str(bar.ts),
                    },
                )
            if not decision.allowed:
                self.event_store.append("risk", make_event(RiskEvent, "RISK_REJECT", symbol, "paper", self.event_store.next_seq("risk"), {"reason": decision.reason}))
                self.ops.inc_metric("orders_rejected_total")
                if decision.flatten:
                    fills_all.append(self.execution.flatten_worst_case(symbol, exposure))
                    exposure = 0.0
                    break
                continue

            adjusted_why = dict(intent.why)
            adjusted_why["risk"] = {"decision_reason": decision.reason, **decision.details}
            adjusted = OrderIntent(intent.symbol, intent.side, decision.adjusted_notional, adjusted_why)
            idem = make_idempotency_key(asdict(adjusted), "perps-intraday", i)
            order_id = f"ord-{i}"
            self.event_store.append("orders", make_event(OrderIntentEvent, "ORDER_INTENT", symbol, "paper", self.event_store.next_seq("orders"), asdict(adjusted), idempotency_key=idem))
            ok_submit, _ = self.oms.submit_intent(ManagedOrder(order_id=order_id, symbol=symbol, side=adjusted.side, notional=adjusted.target_notional, idempotency_key=idem))
            if not ok_submit:
                self.ops.inc_metric("orders_rejected_total")
                continue
            self.oms.transition(order_id, "ACK")
            self.event_store.append("orders", make_event(OrderEvent, "ORDER_ACK", symbol, "paper", self.event_store.next_seq("orders"), {"order_id": order_id}, idempotency_key=idem))

            fills = self.execution.execute_paper(order_id, adjusted, bar.mark_price, bar.depth_notional, oi_spike, bar.liquidations, bar.funding_rate, bar.spread_bps, fc.regime, fc.liquidity_regime)
            if not fills:
                self.ops.inc_metric("orders_rejected_total")
                continue

            for fill in fills:
                self.oms.apply_fill(order_id, fill.notional)
                self.event_store.append("fills", make_event(FillEvent, "FILL", symbol, "paper", self.event_store.next_seq("fills"), asdict(fill), idempotency_key=fill.fill_id))
                fills_all.append(fill)

            fill_notional = sum(f.notional for f in fills)
            fees = sum(f.fee + f.slippage_cost for f in fills)
            funding_paid_pct += abs(bar.funding_rate) * 100
            side = 1 if adjusted.side == "buy" else -1
            ret = side * (bar.mark_price / bars[i - 1].mark_price - 1)
            pnl = fill_notional * ret - fees - abs(bar.funding_rate) * fill_notional
            equity += pnl / max(self.settings.policy.base_risk_budget, 1.0)
            peak = max(peak, equity)
            exposure += fill_notional if adjusted.side == "buy" else -fill_notional
            self.risk.record_return((pnl / max(fill_notional, 1.0)) * 100)
            plans.append({"order_id": order_id, **asdict(adjusted)})
            trade_log.append({"order_id": order_id, "side": adjusted.side, "notional": fill_notional, "pnl": pnl, "why": adjusted.why})
            self.ops.inc_metric("orders_submitted_total")
            strategy_perf = {k: v + pnl / 10000 for k, v in strategy_perf.items()}
            self.policy.update_allocator(strategy_perf)

        rec_ok, rec_reason = self.recon.reconcile(fills_all, exposure, True, True)
        if not rec_ok:
            self.risk.state.kill_switch = True
            self.risk.state.safe_mode = True
            self.event_store.append("risk", make_event(RiskEvent, "RECONCILIATION_MISMATCH", symbol, "paper", self.event_store.next_seq("risk"), {"reason": rec_reason}))
            fills_all.append(self.execution.flatten_worst_case(symbol, exposure))
            exposure = 0.0

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
        self.ops.set_metric("slippage_bps", self.settings.execution.slippage_bps)
        self.ops.set_metric("fees_paid", sum(f.fee for f in fills_all))
        self.ops.set_metric("funding_paid", funding_paid_pct)
        maker_count = len([f for f in fills_all if "maker" in f.status])
        self.ops.set_metric("maker_fill_rate", 0.0 if not fills_all else maker_count / len(fills_all))
        avg_cost = 0.0
        if trade_log:
            vals = []
            for t in trade_log:
                comps = t.get("why", {}).get("components", [])
                vals.extend([c.get("cost_total_bps", 0.0) for c in comps])
            if vals:
                avg_cost = sum(vals) / len(vals)

        self.ops.set_metric("cost_total_bps", avg_cost)
        self.ops.set_metric("crowding_score", getattr(self.risk.state, "last_crowding_score", 0.0))
        self.ops.set_metric("funding_budget_utilization", getattr(self.risk.state, "funding_budget_utilization", 0.0))
        for k, v in self.policy.allocator.state.weights.items():
            self.ops.set_metric(f"allocator_weight_{k}", v)

        inc = self.incidents.evaluate(self.ops.metrics)
        if inc is not None:
            self.notifier.notify(inc.action, inc.reason)

        self.ops.export_prometheus()
        self.raw.write_table("order_plans", plans)
        self.raw.write_table("fills", [asdict(f) for f in fills_all])
        self.raw.write_table("report", [{"equity": equity, "drawdown_pct": drawdown, "drawdown_signed_pct": drawdown_signed, "funding_paid_pct": funding_paid_pct}])
        self.raw.write_table("trade_log", trade_log)

        checksums = {
            "orders_checksum": sha256(json.dumps(plans, sort_keys=True, default=str).encode()).hexdigest(),
            "fills_checksum": sha256(json.dumps([asdict(f) for f in fills_all], sort_keys=True, default=str).encode()).hexdigest(),
            # Keep backward-compatible checksum payload stable for golden tests.
            "equity_checksum": sha256(json.dumps({"equity": equity, "drawdown": drawdown_signed}, sort_keys=True).encode()).hexdigest(),
        }
        self.raw.write_table("checksums", [checksums])
        return {"status": "ok", "orders": len(plans), "fills": len(fills_all), **checksums}
