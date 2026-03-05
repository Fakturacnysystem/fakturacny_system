from __future__ import annotations

from autonomous_investment_robot.connectors.cex.kraken_fix_adapter import KrakenFixAdapter
from autonomous_investment_robot.connectors.cex.kraken_futures import KrakenFuturesConnector, KrakenFuturesSettings


def test_kraken_futures_market_snapshot_parses_ticker(monkeypatch) -> None:
    c = KrakenFuturesConnector(KrakenFuturesSettings())

    def _tickers():
        return {
            "tickers": [
                {
                    "symbol": "PI_XBTUSD",
                    "bid": 67000.0,
                    "ask": 67010.0,
                    "markPrice": 67005.0,
                    "indexPrice": 67002.0,
                    "fundingRate": 0.0001,
                    "openInterest": 12345.0,
                    "volume24h": 987654.0,
                }
            ]
        }

    monkeypatch.setattr(c, "tickers", _tickers)
    snap = c.market_snapshot("PI_XBTUSD")
    assert snap["mid"] > 0.0
    assert snap["funding_rate"] == 0.0001
    assert snap["open_interest"] == 12345.0


def test_fix_adapter_disabled_by_default() -> None:
    fix = KrakenFixAdapter()
    try:
        fix.connect()
    except RuntimeError as exc:
        assert "disabled" in str(exc).lower()
    else:
        raise AssertionError("Expected RuntimeError for disabled FIX adapter")
