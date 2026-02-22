import os

import pytest

from autonomous_investment_robot.config.settings import (
    BinanceExecutionSettings,
    ExecutionSettings,
    LiveUnlockSettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    TCOSettings,
)
from autonomous_investment_robot.services.execution.live_binance_service import LiveBinanceService
from autonomous_investment_robot.services.policy.service import OrderIntent


class FakeConnector:
    def __init__(self):
        self.orders = {}
        self.place_calls = 0
        self.cancel_calls = 0
        self.fail_place = False
        self.fail_with_rate_limit = False
        self.next_order_status = "NEW"
        self.positions = []
        self._open_orders = []

    @property
    def has_credentials(self):
        return True

    def verify_live_permissions(self):
        return True, "ok"

    def exchange_info(self):
        return {"symbols": [{"symbol": "BTCUSDT"}]}

    def set_leverage(self, symbol, leverage):
        return {"symbol": symbol, "leverage": leverage}

    def book_ticker(self, symbol):
        return {"bidPrice": "100.0", "askPrice": "100.1", "bidQty": "10", "askQty": "10"}

    def query_order(self, symbol, client_order_id):
        if client_order_id in self.orders:
            return self.orders[client_order_id]
        raise RuntimeError("not found")

    def place_order(self, params):
        self.place_calls += 1
        if self.fail_with_rate_limit:
            raise RuntimeError("429 Too many requests")
        if self.fail_place:
            raise RuntimeError("reject")
        cid = params["newClientOrderId"]
        if params.get("type") == "MARKET":
            order = {"clientOrderId": cid, "status": "FILLED"}
        else:
            order = {"clientOrderId": cid, "status": self.next_order_status}
        self.orders[cid] = order
        return order

    def cancel_order(self, symbol, client_order_id):
        self.cancel_calls += 1
        return {"status": "CANCELED"}

    def open_orders(self, symbol=None):  # noqa: ARG002
        return list(self._open_orders)

    def position_risk(self, symbol=None):
        return self.positions


def _settings(mode="live_testnet"):
    return RobotSettings(
        provider_whitelist=["binance_um_perps"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode=mode,
            binance=BinanceExecutionSettings(
                allow_unknown_permissions=True,
                maker_timeout_s=0,
                taker_fallback=True,
            ),
        ),
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(
                enable_live_trading=True,
                ack_i_understand_risks=True,
                require_testnet_passed=False,
                canary_required_before_full=True,
            )
        ),
        risk=RiskLimits(
            max_daily_loss_pct=5.0,
            max_drawdown_pct=10.0,
            max_position_notional=1000.0,
            max_exposure_notional=2000.0,
            max_orders_per_min=10,
            leverage=0,
            max_spread_bps=20.0,
            min_depth_notional=100.0,
            stale_data_seconds=60.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=3.0,
            max_liquidation_spike=100000.0,
            divergence_threshold_bps=30.0,
            crowding_score_kill=25.0,
        ),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )


def test_live_unlock_fail_closed_when_flags_false(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    with pytest.raises(ValueError):
        RobotSettings(
            provider_whitelist=["binance_um_perps"],
            execution=ExecutionSettings(mode="live_testnet"),
            safety=SafetySettings(
                live_unlock=LiveUnlockSettings(
                    enable_live_trading=False,
                    ack_i_understand_risks=False,
                    require_testnet_passed=False,
                )
            ),
            risk=_settings().risk,
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_live_fails_when_secrets_missing(monkeypatch):
    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("EXCHANGE_API_SECRET", raising=False)
    with pytest.raises(ValueError):
        _settings()


def test_idempotency_client_order_id_is_deterministic(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    svc = LiveBinanceService(_settings(), run_id="r1", connector=FakeConnector())
    a = svc._client_order_id("BTCUSDT", "buy", 1700000000.0, 0)
    b = svc._client_order_id("BTCUSDT", "buy", 1700000000.0, 0)
    assert a == b
    assert len(a) == 32


def test_retry_like_reentry_never_double_places(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    monkeypatch.setattr("autonomous_investment_robot.services.execution.live_binance_service.time.time", lambda: 1700000000.0)
    intent = OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={})
    first = svc.execute_intent(intent)
    placed_after_first = fake.place_calls
    second = svc.execute_intent(intent)

    assert first.status in {"filled_maker", "filled_taker_fallback", "timeout", "deduped"}
    assert second.status == "deduped"
    assert fake.place_calls == placed_after_first


def test_reject_storm_triggers_kill_and_cooldown(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.fail_place = True
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)
    intent = OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={})

    last = None
    for _ in range(7):
        last = svc.execute_intent(intent)
    assert last is not None
    assert last.status == "killed"
    assert svc.safe_mode is True


def test_maker_timeout_falls_back_to_taker(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.next_order_status = "NEW"
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    result = svc.execute_intent(OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={}))
    assert result.status == "filled_taker_fallback"
    assert fake.cancel_calls >= 1


def test_reconciliation_mismatch_sets_safe_mode_and_flatten(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.positions = [{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    ok, _ = svc.reconcile_live_state(internal_exposure=1.0)
    assert ok is False
    assert svc.safe_mode is True

    fake.positions = [{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]

    def _position_risk(symbol=None):
        if fake.positions:
            out = fake.positions
            fake.positions = []
            return out
        return []

    fake.position_risk = _position_risk
    closed, reason = svc.flatten_all_positions(max_attempts=2)
    assert closed is True
    assert reason == "flat"


def test_rate_limit_storm_triggers_kill(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.fail_with_rate_limit = True
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)
    intent = OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={})
    last = None
    for _ in range(5):
        last = svc.execute_intent(intent)
    assert last is not None
    assert last.status == "killed"
    assert last.reason == "rate_limit_storm"
    assert svc.killed is True
    assert svc.safe_mode is True


def test_flatten_cancels_open_orders_best_effort(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake._open_orders = [{"symbol": "BTCUSDT", "clientOrderId": "abc"}]
    fake.positions = []
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)
    closed, reason = svc.flatten_all_positions()
    assert closed is True
    assert reason == "flat"
    assert fake.cancel_calls >= 1


def test_reconcile_and_flatten_on_mismatch(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    fake = FakeConnector()
    fake.positions = [{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]
    svc = LiveBinanceService(_settings(), run_id="r1", connector=fake)

    calls = {"n": 0}

    def _position_risk(symbol=None):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"symbol": "BTCUSDT", "positionAmt": "1.0", "markPrice": "100.0"}]
        return []

    fake.position_risk = _position_risk
    ok, reason = svc.reconcile_and_flatten_on_mismatch(internal_exposure=0.0, max_flatten_attempts=2)
    assert ok is False
    assert "flattened" in reason
    assert svc.killed is True


@pytest.mark.integration
def test_testnet_minimal_order_cycle_opt_in(monkeypatch):
    if os.getenv("RUN_TESTNET", "0") != "1":
        pytest.skip("set RUN_TESTNET=1 to run integration testnet test")
    pytest.skip("integration skeleton: configure real testnet credentials and endpoint")
