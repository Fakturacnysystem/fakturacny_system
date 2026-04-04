from __future__ import annotations

import sys
from types import SimpleNamespace

from autonomous_investment_robot.config.settings import KrakenSpotExecutionSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import KrakenSpotConnector


class _FakeKrakenExchange:
    def __init__(self, payload):
        self.payload = payload
        self.options = {}
        self.last_create_order: dict | None = None

    def load_markets(self):
        return None

    def market(self, symbol):  # noqa: ARG002
        return {"symbol": "SOL/EUR", "id": "SOLEUR"}

    def create_order(self, symbol, order_type, side, amount, price, params):
        self.last_create_order = {
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "price": price,
            "params": dict(params),
        }
        return {
            "id": "oid-1",
            "symbol": symbol,
            "status": "open",
            "side": side,
            "filled": 0.0,
            "average": 0.0,
            "info": {
                "txid": "oid-1",
                "status": "open",
                "cl_ord_id": params.get("cl_ord_id", ""),
                "userref": params.get("userref", ""),
                "descr": {"pair": symbol, "type": side},
            },
        }


def _connector(monkeypatch):
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    holder: dict[str, _FakeKrakenExchange] = {}

    def _factory(payload):
        exchange = _FakeKrakenExchange(payload)
        holder["exchange"] = exchange
        return exchange

    monkeypatch.setitem(sys.modules, "ccxt", SimpleNamespace(kraken=_factory))
    connector = KrakenSpotConnector(KrakenSpotExecutionSettings())
    return connector, holder


def test_kraken_spot_validate_order_preview_omits_userref(monkeypatch):
    connector, holder = _connector(monkeypatch)

    ok, reason = connector.validate_order_preview(symbol="SOL/EUR", side="buy", amount=1.0, price=100.0, post_only=True)

    assert ok is True
    assert reason == "validated"
    params = holder["exchange"].last_create_order["params"]
    assert params["validate"] is True
    assert params["postOnly"] is True
    assert "userref" not in params


def test_kraken_spot_place_order_prefers_cl_ord_id_over_userref(monkeypatch):
    connector, holder = _connector(monkeypatch)

    out = connector.place_order(
        {
            "symbol": "SOL/EUR",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": "1.0",
            "price": "100.0",
            "postOnly": True,
            "newClientOrderId": "cid-1",
        }
    )

    params = holder["exchange"].last_create_order["params"]
    assert params["cl_ord_id"] == "cid-1"
    assert "userref" not in params
    assert out["clientOrderId"] == "cid-1"
    assert out["status"] == "NEW"
