import base64
import json

from autonomous_investment_robot.config.settings import KrakenExecutionSettings
from autonomous_investment_robot.connectors.cex.kraken_derivatives import KrakenDerivativesConnector


def _connector(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", base64.b64encode(b"secret-32-bytes-material").decode("ascii"))
    return KrakenDerivativesConnector(KrakenExecutionSettings())


def test_signature_endpoint_path_normalization():
    assert KrakenDerivativesConnector._signature_endpoint_path("/derivatives/api/v3/sendorder") == "/api/v3/sendorder"
    assert KrakenDerivativesConnector._signature_endpoint_path("/api/v3/sendorder") == "/api/v3/sendorder"


def test_authent_is_deterministic(monkeypatch):
    c = _connector(monkeypatch)
    a = c._authent("/api/v3/sendorder", "symbol=PI_XBTUSD&size=1", "1700000000000")
    b = c._authent("/api/v3/sendorder", "symbol=PI_XBTUSD&size=1", "1700000000000")
    assert a == b
    assert isinstance(a, str)
    assert len(a) > 10


def test_place_order_normalizes_send_status(monkeypatch):
    c = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        assert path == "/derivatives/api/v3/sendorder"
        assert signed is True
        return {"result": "success", "sendStatus": {"status": "placed", "cliOrdId": "cid1", "order_id": "o1"}}

    c._request = _fake_request  # type: ignore[method-assign]
    out = c.place_order(
        {
            "symbol": "PI_XBTUSD",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": "1.0",
            "price": "100.0",
            "postOnly": True,
            "newClientOrderId": "cid1",
        }
    )
    assert out["clientOrderId"] == "cid1"
    assert out["status"] == "NEW"


def test_query_order_normalizes_status(monkeypatch):
    c = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        assert path == "/derivatives/api/v3/orders/status"
        return {
            "result": "success",
            "orders": [{"cliOrdId": "cid1", "order_id": "o1", "status": "partially_filled"}],
        }

    c._request = _fake_request  # type: ignore[method-assign]
    out = c.query_order("PI_XBTUSD", "cid1")
    assert out["clientOrderId"] == "cid1"
    assert out["status"] == "PARTIALLY_FILLED"


def test_open_positions_and_open_orders_normalized(monkeypatch):
    c = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        if path.endswith("/openpositions"):
            return {
                "result": "success",
                "openPositions": [{"symbol": "PI_XBTUSD", "side": "short", "size": 2, "markPrice": 101}],
            }
        if path.endswith("/openorders"):
            return {
                "result": "success",
                "openOrders": [{"symbol": "PI_XBTUSD", "cliOrdId": "cid1", "status": "open"}],
            }
        raise AssertionError(path)

    c._request = _fake_request  # type: ignore[method-assign]
    pos = c.position_risk("PI_XBTUSD")
    oo = c.open_orders("PI_XBTUSD")
    assert pos[0]["positionAmt"] == "-2.0"
    assert pos[0]["markPrice"] == "101"
    assert oo[0]["clientOrderId"] == "cid1"


def test_balances_normalized(monkeypatch):
    c = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        assert path.endswith("/accounts")
        return {
            "result": "success",
            "accounts": [{"currency": "USD", "balanceValue": "123.4", "available": "120.0", "equity": "124.0"}],
        }

    c._request = _fake_request  # type: ignore[method-assign]
    out = c.balances()
    assert out[0]["asset"] == "USD"
    assert out[0]["balance"] == "123.4"
    assert out[0]["availableBalance"] == "120.0"


def test_verify_live_permissions_requires_override_when_unknown(monkeypatch):
    c = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        return {"result": "success", "foo": "bar"}

    c._request = _fake_request  # type: ignore[method-assign]
    ok, reason = c.verify_live_permissions()
    assert ok is False
    assert "unverified" in reason

    c.settings.allow_unknown_permissions = True
    ok2, _ = c.verify_live_permissions()
    assert ok2 is True


def test_fills_history_uses_documented_endpoint(monkeypatch):
    c = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        assert method == "GET"
        assert path == "/derivatives/api/v3/fills"
        assert signed is True
        assert params["lastFillTime"] == 1700000000000
        return {"result": "success", "fills": [{"fillType": "taker"}]}

    c._request = _fake_request  # type: ignore[method-assign]

    rows = c.fills(last_fill_time=1700000000000)

    assert rows[0]["fillType"] == "taker"


def test_execution_events_uses_history_v3_endpoint(monkeypatch):
    c = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        assert method == "GET"
        assert path == "/api/history/v3/executions"
        assert signed is True
        assert params["since"] == 1700000000000
        assert params["count"] == 50
        return {"events": []}

    c._request = _fake_request  # type: ignore[method-assign]

    out = c.execution_events(since=1700000000000, count=50)

    assert out == {"events": []}


def test_account_log_uses_history_v3_endpoint(monkeypatch):
    c = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        assert method == "GET"
        assert path == "/api/history/v3/account-log"
        assert signed is True
        assert params["since"] == 1700000000000
        return {"logs": [{"execution": "exec-1", "realized_pnl": 2.5}]}

    c._request = _fake_request  # type: ignore[method-assign]

    rows = c.account_log(since=1700000000000)

    assert rows[0]["execution"] == "exec-1"
