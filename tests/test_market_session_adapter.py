from __future__ import annotations

from datetime import datetime, timezone

from autonomous_investment_robot.services.execution.live_kraken_spot_service import MarketSessionAdapter


def test_xstock_session_blocks_on_weekend() -> None:
    adapter = MarketSessionAdapter(enabled=True, is_xstock_pair=lambda _pair: True)
    ts = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc).timestamp()  # Saturday
    ok, reason = adapter.is_open("TSLAXUSD", ts=ts)
    assert ok is False
    assert reason == "xstock_weekend_closed"


def test_xstock_session_allows_during_market_hours() -> None:
    adapter = MarketSessionAdapter(enabled=True, is_xstock_pair=lambda _pair: True)
    ts = datetime(2026, 3, 9, 15, 0, tzinfo=timezone.utc).timestamp()  # Monday
    ok, reason = adapter.is_open("TSLAXUSD", ts=ts)
    assert ok is True
    assert reason == "xstock_session_open"


def test_crypto_pair_is_always_open() -> None:
    adapter = MarketSessionAdapter(enabled=True, is_xstock_pair=lambda _pair: False)
    ts = datetime(2026, 3, 8, 2, 0, tzinfo=timezone.utc).timestamp()
    ok, reason = adapter.is_open("XBTUSD", ts=ts)
    assert ok is True
    assert reason == "always_open_24_7"
