import json

from autonomous_investment_robot.services.governance.service import GovernanceService
from autonomous_investment_robot.services.reliability.bus import ReliabilityBus
from autonomous_investment_robot.services.treasury.service import TreasuryService


def test_treasury_throttles_when_reserve_is_low():
    svc = TreasuryService(reserve_cash_ratio=0.2, min_margin_buffer=1.2)
    out = svc.evaluate(quote_free=50.0, quote_total=1000.0, margin_used=500.0, open_notional=1200.0, drawdown_pct=-4.0)
    assert out.throttle_scale < 1.0
    assert out.reserve_ratio < 0.2
    assert "increase_cash_reserve" in out.actions


def test_governance_constraints_and_reports(tmp_path):
    svc = GovernanceService(str(tmp_path), jurisdiction="SK")
    dec = svc.enforce_policy_constraints(
        symbol="XBTEUR",
        target_notional=1500.0,
        max_notional=1000.0,
        leverage=1,
        max_leverage=1,
        drawdown_pct=-1.0,
        max_drawdown_pct=10.0,
        allowed_symbols={"XBTEUR"},
    )
    assert dec.allowed is False
    assert dec.reason == "mandate_notional_limit"

    report_path = svc.write_compliance_report(
        provider="kraken_spot",
        provider_permissions={"trade": True},
        rules={"max_notional": 1000.0},
    )
    payload = json.loads(open(report_path, encoding="utf-8").read())
    assert payload["provider"] == "kraken_spot"


def test_reliability_bus_exactly_once_and_replay(tmp_path):
    bus = ReliabilityBus(str(tmp_path), max_attempts=2)
    ev1 = bus.publish("orders", {"id": 1}, event_id="e1", idempotency_key="k1")
    ev2 = bus.publish("orders", {"id": 1}, event_id="e2", idempotency_key="k1")
    assert ev1 is not None
    assert ev2 is None

    got = []
    delivered, failed = bus.drain("orders", lambda payload: got.append(payload["id"]))
    assert delivered == 1
    assert failed == 0
    assert got == [1]

    replayed = bus.replay("orders")
    assert len(replayed) == 1
    assert replayed[0].event_id == "e1"
