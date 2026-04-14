from autonomous_investment_robot.services.live_runtime.order_lifecycle import OrderLifecycleMirror


def test_order_lifecycle_mirror_accepts_valid_transitions():
    mirror = OrderLifecycleMirror(venue="binance_um_perps")

    ok, reason = mirror.submit(symbol="BTCUSDT", order_key="cid-1", metadata={"side": "buy"})
    assert (ok, reason) == (True, "ok")

    ok, reason = mirror.apply_exchange_update(
        {"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "NEW"}
    )
    assert (ok, reason) == (True, "ok")

    ok, reason = mirror.apply_exchange_update(
        {"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "PARTIALLY_FILLED"}
    )
    assert (ok, reason) == (True, "ok")

    ok, reason = mirror.apply_exchange_update(
        {"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "FILLED"}
    )
    assert (ok, reason) == (True, "ok")

    snapshot = mirror.snapshot()
    assert snapshot[0]["state"] == "filled"
    assert snapshot[0]["order_id"] == "ord-1"


def test_order_lifecycle_mirror_rejects_out_of_order_update():
    mirror = OrderLifecycleMirror(venue="binance_um_perps")
    mirror.submit(symbol="BTCUSDT", order_key="cid-1")
    ok1, reason1 = mirror.apply_exchange_update({"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "FILLED"})

    ok, reason = mirror.apply_exchange_update(
        {"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "NEW"}
    )

    assert (ok1, reason1) == (True, "ok")
    assert (ok, reason) == (False, "out_of_order_lifecycle_event")


def test_order_lifecycle_mirror_marks_duplicate_events_without_state_mutation():
    mirror = OrderLifecycleMirror(venue="binance_um_perps")
    mirror.submit(symbol="BTCUSDT", order_key="cid-1")
    mirror.apply_exchange_update({"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "NEW"})

    ok, reason = mirror.apply_exchange_update(
        {"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "NEW"}
    )

    assert (ok, reason) == (False, "duplicate_lifecycle_event")
    assert mirror.snapshot()[0]["state"] == "accepted"


def test_order_lifecycle_mirror_normalizes_supported_replace_states():
    mirror = OrderLifecycleMirror(venue="binance_um_perps")
    mirror.submit(symbol="BTCUSDT", order_key="cid-1")
    mirror.apply_exchange_update({"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "NEW"})

    ok_pending, reason_pending = mirror.apply_exchange_update(
        {
            "clientOrderId": "cid-1",
            "orderId": "ord-1",
            "symbol": "BTCUSDT",
            "status": "REPLACE_PENDING",
            "replaceSupported": True,
        }
    )
    ok_replaced, reason_replaced = mirror.apply_exchange_update(
        {
            "clientOrderId": "cid-1",
            "orderId": "ord-1",
            "symbol": "BTCUSDT",
            "status": "REPLACED",
            "replaceSupported": True,
        }
    )

    assert (ok_pending, reason_pending) == (True, "ok")
    assert (ok_replaced, reason_replaced) == (True, "ok")
    assert mirror.snapshot()[0]["state"] == "replaced"


def test_order_lifecycle_mirror_fails_closed_on_unsupported_replace():
    mirror = OrderLifecycleMirror(venue="binance_um_perps")
    mirror.submit(symbol="BTCUSDT", order_key="cid-1")
    mirror.apply_exchange_update({"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "NEW"})

    ok, reason = mirror.apply_exchange_update(
        {"clientOrderId": "cid-1", "orderId": "ord-1", "symbol": "BTCUSDT", "status": "REPLACE_PENDING"}
    )

    assert (ok, reason) == (False, "unsupported_replace")
    assert mirror.snapshot()[0]["state"] == "accepted"


def test_order_lifecycle_mirror_rehydrates_historical_transition_without_pending_side_effects():
    mirror = OrderLifecycleMirror(venue="kraken_spot")

    ok, reason = mirror.rehydrate_transition(
        {
            "symbol": "BTC/USD",
            "order_key": "cid-1",
            "to_state": "timed_out",
            "source": "local_timeout",
            "ts": "2026-04-04T22:00:00+00:00",
            "metadata": {"raw": {"orderId": "ord-1", "clientOrderId": "cid-1"}},
        }
    )

    assert (ok, reason) == (True, "ok")
    assert mirror.drain_transitions() == []
    snapshot = mirror.snapshot()
    assert snapshot[0]["state"] == "timed_out"
    assert snapshot[0]["order_id"] == "ord-1"


def test_order_lifecycle_mirror_promotes_timed_out_order_to_filled_when_fill_truth_arrives():
    mirror = OrderLifecycleMirror(venue="kraken_spot")

    ok, reason = mirror.rehydrate_transition(
        {
            "symbol": "BTC/USD",
            "order_key": "cid-1",
            "to_state": "timed_out",
            "source": "local_timeout",
            "ts": "2026-04-04T22:00:00+00:00",
            "metadata": {"raw": {"orderId": "ord-1", "clientOrderId": "cid-1"}},
        }
    )
    assert (ok, reason) == (True, "ok")

    ok, reason = mirror.fill_confirmed(
        symbol="BTC/USD",
        order_key="ord-1",
        order_id="ord-1",
        client_order_id="cid-1",
        metadata={"raw": {"fillId": "fill-1"}},
    )

    assert (ok, reason) == (True, "ok")
    snapshot = mirror.snapshot()
    assert snapshot[0]["state"] == "filled"
    assert snapshot[0]["order_id"] == "ord-1"
    assert snapshot[0]["fill_count"] == 1
