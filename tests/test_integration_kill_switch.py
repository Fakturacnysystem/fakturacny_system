from autonomous_investment_robot.services.execution.service import Fill
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService


def test_reconciliation_mismatch_triggers_kill_path_signal():
    rec = ReconciliationService()
    fills = [Fill("paper", "o1", "f1", "BTCUSDT", "buy", 100.0, 0.1, 0.2, 100, "filled")]
    ok, reason = rec.reconcile(fills, internal_exposure=0.0, open_orders_state_ok=True, cash_ok=True)
    assert ok is False
    assert reason == "position_mismatch"
