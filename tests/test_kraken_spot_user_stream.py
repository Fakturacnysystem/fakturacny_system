from __future__ import annotations

from autonomous_investment_robot.services.event_store.service import EventStore
from autonomous_investment_robot.services.execution.kraken_spot_user_stream import KrakenSpotUserStream


class FakeKrakenSpotWsConnector:
    def get_websockets_token(self) -> str:
        return "tok-123"

    def symbol_from_market_id(self, market_id: str) -> str:
        return "BTC/USD" if market_id in {"XBT/USD", "XXBTZUSD"} else market_id


def test_kraken_spot_user_stream_builds_subscription_messages(tmp_path) -> None:
    stream = KrakenSpotUserStream(
        connector=FakeKrakenSpotWsConnector(),
        event_store=EventStore(str(tmp_path)),
        run_dir=str(tmp_path),
        ws_private_url="wss://ws-auth.kraken.com/",
    )

    messages = stream.subscription_messages("tok-123")

    assert messages == [
        {"event": "subscribe", "subscription": {"name": "openOrders", "token": "tok-123"}},
        {"event": "subscribe", "subscription": {"name": "ownTrades", "token": "tok-123"}},
    ]


def test_kraken_spot_user_stream_tracks_subscription_state_and_parses_private_events(tmp_path) -> None:
    order_updates: list[dict] = []
    fill_updates: list[dict] = []
    states: list[dict] = []
    stream = KrakenSpotUserStream(
        connector=FakeKrakenSpotWsConnector(),
        event_store=EventStore(str(tmp_path)),
        run_dir=str(tmp_path),
        ws_private_url="wss://ws-auth.kraken.com/",
        on_order_update=order_updates.append,
        on_fill_update=fill_updates.append,
        on_state_change=states.append,
    )

    stream.handle_message(
        {
            "event": "subscriptionStatus",
            "status": "subscribed",
            "subscription": {"name": "openOrders"},
            "channelName": "openOrders",
        }
    )
    assert stream.connected is False

    stream.handle_message(
        {
            "event": "subscriptionStatus",
            "status": "subscribed",
            "subscription": {"name": "ownTrades"},
            "channelName": "ownTrades",
        }
    )
    assert stream.connected is True
    assert states[-1]["connected"] is True

    stream.handle_message(
        [
            [
                {
                    "OID-1": {
                        "avg_price": "110.10",
                        "cl_ord_id": "cid-77",
                        "descr": {"pair": "XBT/USD", "type": "buy"},
                        "status": "open",
                        "userref": "77",
                        "vol": "0.10",
                        "vol_exec": "0.00",
                    }
                }
            ],
            "openOrders",
            {"sequence": 5},
        ]
    )
    stream.handle_message(
        [
            [
                {
                    "TID-1": {
                        "cost": "11.01",
                        "ordertxid": "OID-1",
                        "pair": "XBT/USD",
                        "price": "110.10",
                        "time": "1700000000.0",
                        "vol": "0.10",
                    }
                }
            ],
            "ownTrades",
            {"sequence": 6},
        ]
    )

    assert stream.open_orders_seeded is True
    assert order_updates[0]["clientOrderId"] == "cid-77"
    assert order_updates[0]["orderId"] == "OID-1"
    assert order_updates[0]["status"] == "NEW"
    assert order_updates[0]["symbol"] == "BTC/USD"
    assert order_updates[0]["raw"]["userref"] == "77"
    assert fill_updates[0]["fill_id"] == "TID-1"
    assert fill_updates[0]["order_id"] == "OID-1"
    assert fill_updates[0]["notional"] == 11.01
