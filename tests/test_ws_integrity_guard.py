from __future__ import annotations

from autonomous_investment_robot.services.marketdata.ws_integrity import WSDataIntegrityGuard


def test_ws_dedupe_trade_ids() -> None:
    guard = WSDataIntegrityGuard(stale_after_s=10.0, max_out_of_order=5)
    assert guard.record_trade(stream="spot_trade", trade_id="t1", ts=100.0) is True
    assert guard.record_trade(stream="spot_trade", trade_id="t1", ts=101.0) is False
    snap = guard.snapshot(now_ts=101.0)
    assert snap["streams"]["spot_trade"]["duplicates"] >= 1


def test_ws_latency_budget_pauses_entries() -> None:
    guard = WSDataIntegrityGuard(stale_after_s=2.0, max_out_of_order=5)
    guard.record_stream_update(stream="spot_book", ts=10.0)
    snap_ok = guard.snapshot(now_ts=11.0)
    assert snap_ok["healthy"] is True
    snap_bad = guard.snapshot(now_ts=20.0)
    assert snap_bad["healthy"] is False
    assert snap_bad["streams"]["spot_book"]["stale"] is True
