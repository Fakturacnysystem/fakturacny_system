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


def test_oms_rejects_non_positive_fill_and_overfill():
    oms = OMSService()
    order = ManagedOrder(order_id="o3", symbol="BTCUSDT", side="buy", notional=100, idempotency_key="k3")
    oms.submit_intent(order)
    oms.transition("o3", "ACK")

    ok_zero, reason_zero = oms.apply_fill("o3", 0, "f0")
    assert ok_zero is False
    assert reason_zero == "non_positive_fill_notional"

    ok_negative, reason_negative = oms.apply_fill("o3", -10, "f1")
    assert ok_negative is False
    assert reason_negative == "non_positive_fill_notional"

    ok_valid, _ = oms.apply_fill("o3", 90, "f2")
    assert ok_valid is True
    ok_overfill, reason_overfill = oms.apply_fill("o3", 20, "f3")
    assert ok_overfill is False
    assert reason_overfill == "overfill_notional"


def test_oms_rejects_duplicate_fill_id():
    oms = OMSService()
    order = ManagedOrder(order_id="o4", symbol="BTCUSDT", side="buy", notional=100, idempotency_key="k4")
    oms.submit_intent(order)
    oms.transition("o4", "ACK")

    ok_first, _ = oms.apply_fill("o4", 40, "f-dup")
    ok_dup, reason_dup = oms.apply_fill("o4", 10, "f-dup")
    assert ok_first is True
    assert ok_dup is False
    assert reason_dup == "duplicate_fill_id"


def test_oms_emits_lifecycle_snapshot_and_cancel_path():
    oms = OMSService()
    order = ManagedOrder(order_id="o5", symbol="BTCUSDT", side="buy", notional=100, idempotency_key="k5")
    ok_submit, _ = oms.submit_intent(order)
    assert ok_submit is True
    oms.transition("o5", "ACK")
    ok_cancel, _ = oms.request_cancel("o5")
    assert ok_cancel is True
    ok_reject, _ = oms.reject_cancel("o5", "venue_busy")
    assert ok_reject is True
    snapshot = oms.lifecycle_snapshot()
    assert snapshot
    assert any(item["state"] == "cancel_rejected" for item in snapshot)
    transitions = oms.drain_lifecycle_transitions()
    assert transitions
