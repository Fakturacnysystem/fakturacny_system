from autonomous_investment_robot.services.oms.service import ManagedOrder, OMSService


def test_oms_idempotency_duplicate_submit():
    oms = OMSService()
    order = ManagedOrder(order_id="o1", symbol="BTCUSDT", side="buy", notional=100, idempotency_key="same")
    ok1, _ = oms.submit_intent(order)
    ok2, reason = oms.submit_intent(order)
    assert ok1 is True
    assert ok2 is False
    assert reason == "duplicate_submit"


def test_oms_partial_to_filled_transition():
    oms = OMSService()
    order = ManagedOrder(order_id="o2", symbol="BTCUSDT", side="buy", notional=100, idempotency_key="k2")
    oms.submit_intent(order)
    oms.transition("o2", "ACK")
    ok, _ = oms.apply_fill("o2", 40)
    assert ok is True and oms.orders["o2"].state == "PARTIAL"
    ok, _ = oms.apply_fill("o2", 60)
    assert ok is True and oms.orders["o2"].state == "FILLED"
