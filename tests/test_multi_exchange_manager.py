from __future__ import annotations

from autonomous_investment_robot.services.multi_exchange.exchange_manager import ExchangeManager


def test_multi_exchange_manager_disabled_defaults() -> None:
    mgr = ExchangeManager(enabled=False)
    st = mgr.initialize()
    assert all(not x.enabled for x in st.values())


def test_multi_exchange_route_venue_scores() -> None:
    mgr = ExchangeManager(enabled=True)
    dec = mgr.route_venue(
        symbol="XBTUSD",
        candidates=[
            {"venue": "a", "liquidity": 100.0, "fee_bps": 20.0, "spread_bps": 5.0},
            {"venue": "b", "liquidity": 200.0, "fee_bps": 50.0, "spread_bps": 10.0},
        ],
    )
    assert dec.venue == "b"
