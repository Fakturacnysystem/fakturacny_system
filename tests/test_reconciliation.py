from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import TruthConfidence, TruthConfidenceLevel, TruthConfidenceSnapshot
from autonomous_investment_robot.services.execution.service import Fill
from autonomous_investment_robot.services.reconciliation.service import ReconciliationAction, ReconciliationService, ReconciliationSeverity


def _fill(order_id: str, side: str, notional: float) -> Fill:
    return Fill(
        venue="paper",
        order_id=order_id,
        fill_id=f"{order_id}-f",
        symbol="BTCUSDT",
        side=side,
        notional=notional,
        fee=0.0,
        slippage_cost=0.0,
        latency_ms=10,
        status="filled",
    )


def _truth_snapshot(
    *,
    fill: TruthConfidenceLevel = TruthConfidenceLevel.AUTHORITATIVE,
    fee: TruthConfidenceLevel = TruthConfidenceLevel.AUTHORITATIVE,
    realized: TruthConfidenceLevel = TruthConfidenceLevel.AUTHORITATIVE,
    balance: TruthConfidenceLevel = TruthConfidenceLevel.AUTHORITATIVE,
    exposure: TruthConfidenceLevel = TruthConfidenceLevel.AUTHORITATIVE,
    market: TruthConfidenceLevel = TruthConfidenceLevel.AUTHORITATIVE,
) -> TruthConfidenceSnapshot:
    ts = datetime.now(timezone.utc)
    return TruthConfidenceSnapshot(
        ts=ts,
        fill_truth_confidence=TruthConfidence("fill_truth_confidence", fill, "test"),
        fee_truth_confidence=TruthConfidence("fee_truth_confidence", fee, "test"),
        realized_pnl_confidence=TruthConfidence("realized_pnl_confidence", realized, "test"),
        balance_truth_confidence=TruthConfidence("balance_truth_confidence", balance, "test"),
        exposure_truth_confidence=TruthConfidence("exposure_truth_confidence", exposure, "test"),
        market_data_truth_confidence=TruthConfidence("market_data_truth_confidence", market, "test"),
    )


def test_reconcile_report_classifies_position_mismatch_as_critical_flatten():
    svc = ReconciliationService()
    report = svc.reconcile_report(
        fills=[_fill("o1", "buy", 100.0)],
        internal_exposure=20.0,
        open_orders_state_ok=True,
        cash_ok=True,
    )
    assert report.ok is False
    assert report.code == "position_mismatch"
    assert report.severity == ReconciliationSeverity.CRITICAL
    assert report.action == ReconciliationAction.HALT_AND_FLATTEN


def test_reconcile_report_classifies_cash_mismatch_as_critical_halt():
    svc = ReconciliationService()
    report = svc.reconcile_report(
        fills=[_fill("o1", "buy", 100.0)],
        internal_exposure=100.0,
        open_orders_state_ok=True,
        cash_ok=False,
    )
    assert report.ok is False
    assert report.code == "cash_mismatch"
    assert report.severity == ReconciliationSeverity.CRITICAL
    assert report.action == ReconciliationAction.HALT


def test_reconcile_legacy_tuple_interface_remains_compatible():
    svc = ReconciliationService()
    ok, reason = svc.reconcile(
        fills=[_fill("o1", "buy", 100.0)],
        internal_exposure=100.0,
        open_orders_state_ok=True,
        cash_ok=True,
    )
    assert ok is True
    assert reason == "ok"


def test_reconcile_live_report_classifies_realized_pnl_mismatch_as_halt():
    svc = ReconciliationService()
    report = svc.reconcile_live_report(
        exchange_exposure=0.0,
        internal_exposure=0.0,
        open_orders_state_ok=True,
        cash_ok=True,
        local_realized_pnl=5.0,
        exchange_realized_pnl=15.0,
    )
    assert report.ok is False
    assert report.code == "live_realized_pnl_mismatch"
    assert report.severity == ReconciliationSeverity.CRITICAL
    assert report.action == ReconciliationAction.HALT


def test_reconcile_live_report_classifies_unrealized_pnl_mismatch_as_alert():
    svc = ReconciliationService()
    report = svc.reconcile_live_report(
        exchange_exposure=100.0,
        internal_exposure=100.0,
        open_orders_state_ok=True,
        cash_ok=True,
        local_unrealized_pnl=2.0,
        exchange_unrealized_pnl=12.0,
    )
    assert report.ok is False
    assert report.code == "live_unrealized_pnl_mismatch"
    assert report.severity == ReconciliationSeverity.WARNING
    assert report.action == ReconciliationAction.ALERT


def test_reconcile_live_judgment_flattens_on_unavailable_fee_truth():
    svc = ReconciliationService()
    judgment = svc.reconcile_live_judgment(
        exchange_exposure=0.0,
        internal_exposure=0.0,
        open_orders_state_ok=True,
        cash_ok=True,
        local_realized_pnl=0.0,
        exchange_realized_pnl=0.0,
        truth_confidence=_truth_snapshot(fee=TruthConfidenceLevel.UNAVAILABLE),
    )

    assert judgment.ok is False
    assert judgment.action == ReconciliationAction.FLATTEN_ONLY.value
    assert any(domain.domain == "fees" and domain.action == ReconciliationAction.FLATTEN_ONLY.value for domain in judgment.domains)


def test_reconcile_live_judgment_degrades_on_proxy_fill_truth():
    svc = ReconciliationService()
    judgment = svc.reconcile_live_judgment(
        exchange_exposure=0.0,
        internal_exposure=0.0,
        open_orders_state_ok=True,
        cash_ok=True,
        local_realized_pnl=0.0,
        exchange_realized_pnl=0.0,
        truth_confidence=_truth_snapshot(fill=TruthConfidenceLevel.PROXY),
    )

    assert judgment.ok is False
    assert judgment.action == ReconciliationAction.DEGRADE.value
    assert any(domain.domain == "fill_completeness" and domain.action == ReconciliationAction.DEGRADE.value for domain in judgment.domains)


def test_reconcile_lifecycle_judgment_flags_orphaned_orders():
    svc = ReconciliationService()
    judgment = svc.reconcile_lifecycle_judgment(
        lifecycle_snapshot=[{"order_key": "cid-1", "state": "orphaned", "confidence": "recovery"}],
        confidence="proxy",
    )
    assert judgment.ok is False
    assert judgment.code == "live_order_lifecycle_mismatch"
    assert judgment.action == ReconciliationAction.FLATTEN_ONLY.value


def test_reconcile_live_report_includes_lifecycle_domain():
    svc = ReconciliationService()
    report = svc.reconcile_live_report(
        exchange_exposure=10.0,
        internal_exposure=10.0,
        open_orders_state_ok=True,
        cash_ok=True,
        lifecycle_snapshot=[{"order_key": "cid-1", "state": "working", "confidence": "exchange"}],
        order_lifecycle_confidence="authoritative",
    )
    domains = report.details["domains"]
    assert any(domain["domain"] == "order_lifecycle_truth" for domain in domains)
