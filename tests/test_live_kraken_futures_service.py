from __future__ import annotations

from autonomous_investment_robot.config.settings import (
    ExecutionSettings,
    LiveUnlockSettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    TCOSettings,
)
from autonomous_investment_robot.services.execution.live_kraken_futures_service import LiveKrakenFuturesService
from autonomous_investment_robot.services.policy.service import OrderIntent


class _FakeFuturesConnector:
    def __init__(self) -> None:
        self._has_credentials = True
        self.bid = 101.0
        self.ask = 101.2
        self.mid = 101.1
        self.mark = 101.1
        self.index = 101.0
        self.funding_rate = 0.0
        self.open_positions_payload = {
            "openPositions": [
                {
                    "symbol": "PI_XBTUSD",
                    "side": "long",
                    "size": 1.0,
                    "entryPrice": 100.0,
                    "unrealizedPnl": 1.1,
                    "realizedPnl": 0.0,
                    "fee": 0.0,
                    "funding": 0.0,
                    "interest": 0.0,
                }
            ]
        }
        self.sent_orders: list[dict] = []

    @property
    def has_credentials(self) -> bool:
        return self._has_credentials

    def instruments(self) -> dict:
        return {
            "instruments": [
                {
                    "symbol": "PI_XBTUSD",
                    "type": "perpetual",
                    "tickSize": 0.5,
                    "contractSize": 0.001,
                    "quote": "USD",
                }
            ]
        }

    def market_snapshot(self, symbol: str) -> dict:
        return {
            "symbol": symbol,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "mark_price": self.mark,
            "index_price": self.index,
            "funding_rate": self.funding_rate,
            "open_interest": 1000.0,
            "volume_24h": 10_000.0,
            "ts": 1.0,
        }

    def orderbook(self, symbol: str, depth: int = 25) -> dict:  # noqa: ARG002
        return {
            "bids": [{"price": self.bid, "size": 5.0}],
            "asks": [{"price": self.ask, "size": 5.0}],
        }

    def open_positions(self) -> dict:
        return self.open_positions_payload

    def account_overview(self) -> dict:
        return {"availableMargin": 1000.0, "currency": "USD"}

    def send_order(self, params: dict) -> dict:
        self.sent_orders.append(dict(params))
        return {"sendStatus": {"status": "placed", "order_id": f"O{len(self.sent_orders)}"}}

    def cancel_all_orders(self) -> dict:
        return {"result": "ok"}


def _settings() -> RobotSettings:
    return RobotSettings(
        provider_whitelist=["kraken_spot"],
        canary_mode=True,
        explicit_live_enable=True,
        ack_live_risks=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            fee_bps=16.0,
            slippage_bps=8.0,
            maker_preference=True,
        ),
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)
        ),
        risk=RiskLimits(
            max_daily_loss_pct=1.0,
            max_weekly_loss_pct=2.0,
            max_drawdown_pct=2.0,
            max_position_notional=1000.0,
            max_exposure_notional=1000.0,
            max_symbol_exposure_notional=1000.0,
            max_cluster_exposure_notional=1000.0,
            max_orders_per_min=10,
            leverage=0,
            max_spread_bps=50.0,
            min_depth_notional=0.0,
            stale_data_seconds=10.0,
            min_margin_buffer=1.0,
            max_funding_cost_per_day=0.0,
            max_oi_spike_pct=0.0,
            max_liquidation_spike=0.0,
            divergence_threshold_bps=50.0,
            crowding_score_kill=50.0,
        ),
        tco=TCOSettings(max_total_cost_bps=50.0, max_impact_bps=20.0),
    )


def test_futures_close_long_blocked_when_below_profit_gate(monkeypatch) -> None:
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeFuturesConnector()
    fake.bid = 101.0
    fake.ask = 101.2
    fake.mid = 101.1
    svc = LiveKrakenFuturesService(_settings(), run_id="r1", connector=fake)

    intent = OrderIntent(symbol="PI_XBTUSD", side="sell", target_notional=100.0, why={})
    out = svc.execute_intent(intent)

    assert out.status == "blocked"
    assert out.reason == "profit_gate_block"
    assert fake.sent_orders == []


def test_futures_close_long_submits_reduce_only_when_profit_gate_passes(monkeypatch) -> None:
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeFuturesConnector()
    fake.bid = 104.5
    fake.ask = 104.7
    fake.mid = 104.6
    fake.mark = 104.6
    svc = LiveKrakenFuturesService(_settings(), run_id="r1", connector=fake)

    intent = OrderIntent(symbol="PI_XBTUSD", side="sell", target_notional=100.0, why={})
    out = svc.execute_intent(intent)

    assert out.status == "submitted"
    assert out.reason == "futures_reduce_only_submitted"
    assert len(fake.sent_orders) == 1
    order = fake.sent_orders[0]
    assert str(order.get("reduceOnly", "")).lower() == "true"
    assert str(order.get("side", "")).lower() == "sell"
    assert str(order.get("orderType", "")).lower() == "lmt"
    assert str(order.get("postOnly", "")).lower() == "true"
    assert float(order.get("limitPrice", 0.0) or 0.0) > 0.0


def test_futures_close_short_uses_short_profit_gate(monkeypatch) -> None:
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeFuturesConnector()
    fake.open_positions_payload = {
        "openPositions": [
            {
                "symbol": "PI_XBTUSD",
                "side": "short",
                "size": 1.0,
                "entryPrice": 100.0,
                "unrealizedPnl": 0.0,
            }
        ]
    }
    fake.bid = 96.9
    fake.ask = 97.0
    fake.mid = 96.95
    svc = LiveKrakenFuturesService(_settings(), run_id="r1", connector=fake)

    intent = OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=100.0, why={})
    out = svc.execute_intent(intent)

    assert out.status == "submitted"
    assert out.reason == "futures_reduce_only_submitted"
    assert len(fake.sent_orders) == 1
    order = fake.sent_orders[0]
    assert str(order.get("side", "")).lower() == "buy"
    assert str(order.get("orderType", "")).lower() == "lmt"
    assert str(order.get("postOnly", "")).lower() == "true"
    assert float(order.get("limitPrice", 0.0) or 0.0) > 0.0


def test_futures_flatten_uses_reduce_only_limit_floor(monkeypatch) -> None:
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeFuturesConnector()
    fake.bid = 105.0
    fake.ask = 105.2
    fake.mid = 105.1
    fake.mark = 105.1
    svc = LiveKrakenFuturesService(_settings(), run_id="r1", connector=fake)

    ok, reason = svc.flatten_all_positions()

    assert ok is True
    assert reason == "flatten_best_effort"
    assert len(fake.sent_orders) == 1
    order = fake.sent_orders[0]
    assert str(order.get("reduceOnly", "")).lower() == "true"
    assert str(order.get("orderType", "")).lower() == "lmt"
    assert float(order.get("limitPrice", 0.0) or 0.0) > 0.0


def test_perps_profit_gate_includes_funding_and_fees(monkeypatch) -> None:
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_FUTURES_FUNDING_BPS_MULTIPLIER", "10.0")
    fake = _FakeFuturesConnector()
    fake.bid = 104.5
    fake.ask = 104.7
    fake.mid = 104.6
    fake.mark = 104.6
    fake.funding_rate = 0.02
    svc = LiveKrakenFuturesService(_settings(), run_id="r1", connector=fake)

    intent = OrderIntent(symbol="PI_XBTUSD", side="sell", target_notional=100.0, why={})
    out = svc.execute_intent(intent)

    assert out.status == "blocked"
    assert out.reason == "profit_gate_block"


def test_futures_exits_only_mode_blocks_new_buys(monkeypatch) -> None:
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = _FakeFuturesConnector()
    svc = LiveKrakenFuturesService(_settings(), run_id="r1", connector=fake)
    svc.set_exits_only_mode(reason="ws_integrity_degraded", duration_s=120.0)

    out = svc.execute_intent(OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=100.0, why={}))
    assert out.status == "blocked"
    assert out.reason == "exits_only_mode"
