from autonomous_investment_robot.config.settings import BinanceExecutionSettings
from autonomous_investment_robot.connectors.cex.binance_um_perps import BinanceUMPerpsConnector


def _connector(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    return BinanceUMPerpsConnector(BinanceExecutionSettings())


def test_user_trades_uses_official_endpoint_and_order_filter(monkeypatch):
    connector = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        assert method == "GET"
        assert path == "/fapi/v1/userTrades"
        assert signed is True
        assert params["symbol"] == "BTCUSDT"
        assert params["orderId"] == 123
        assert params["limit"] == 500
        return [{"id": 1, "orderId": 123, "symbol": "BTCUSDT"}]

    connector._request = _fake_request  # type: ignore[method-assign]

    rows = connector.user_trades("BTCUSDT", order_id=123, limit=500)

    assert rows[0]["orderId"] == 123


def test_income_history_uses_official_endpoint_and_realized_pnl_filter(monkeypatch):
    connector = _connector(monkeypatch)

    def _fake_request(method, path, params=None, signed=False):  # noqa: ARG001
        assert method == "GET"
        assert path == "/fapi/v1/income"
        assert signed is True
        assert params["symbol"] == "BTCUSDT"
        assert params["incomeType"] == "REALIZED_PNL"
        assert params["startTime"] == 1700000000000
        return [{"incomeType": "REALIZED_PNL", "income": "1.5"}]

    connector._request = _fake_request  # type: ignore[method-assign]

    rows = connector.income_history(symbol="BTCUSDT", income_type="REALIZED_PNL", start_time=1700000000000)

    assert rows[0]["income"] == "1.5"
