import os

import pytest

from autonomous_investment_robot.config.settings import (
    ExecutionSettings,
    KrakenExecutionSettings,
    LiveUnlockSettings,
    RiskLimits,
    RobotSettings,
    SafetySettings,
    TCOSettings,
)
from autonomous_investment_robot.services.execution.live_kraken_service import LiveKrakenService
from autonomous_investment_robot.services.policy.service import OrderIntent


class FakeKrakenConnector:
    def __init__(self):
        self._has_credentials = True
        self.supports_live_trading = False
        self.orders = {}
        self.positions = []
        self._open_orders = []
        self.place_calls = 0
        self.cancel_calls = 0
        self.fail_place = False
        self.fail_with_rate_limit = False
        self.next_order_status = "NEW"

    @property
    def has_credentials(self):
        return self._has_credentials

    def verify_live_permissions(self):
        return True, "ok"

    def exchange_info(self):
        return {"symbols": [{"symbol": "PI_XBTUSD"}]}

    def book_ticker(self, symbol):
        return {"bidPrice": "100", "askPrice": "101", "bidQty": "1", "askQty": "1", "symbol": symbol}

    def query_order(self, symbol, client_order_id):  # noqa: ARG002
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
        status = "FILLED" if params.get("type") == "MARKET" else self.next_order_status
        out = {"clientOrderId": cid, "status": status, "symbol": params.get("symbol")}
        self.orders[cid] = out
        return out

    def cancel_order(self, symbol, client_order_id):  # noqa: ARG002
        self.cancel_calls += 1
        return {"status": "CANCELED"}

    def open_orders(self, symbol=None):  # noqa: ARG002
        return list(self._open_orders)

    def position_risk(self, symbol=None):  # noqa: ARG002
        return list(self.positions)


def _limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_pct=1.0,
        max_weekly_loss_pct=2.0,
        max_drawdown_pct=2.0,
        max_position_notional=10.0,
        max_exposure_notional=10.0,
        max_symbol_exposure_notional=10.0,
        max_cluster_exposure_notional=10.0,
        max_orders_per_min=5,
        leverage=0,
        cvar_limit_pct=1.0,
        stress_loss_limit_pct=2.0,
        max_spread_bps=10.0,
        min_depth_notional=10.0,
        stale_data_seconds=10.0,
        min_margin_buffer=2.0,
        max_funding_cost_per_day=1.0,
        max_oi_spike_pct=1.0,
        max_liquidation_spike=1.0,
        divergence_threshold_bps=10.0,
        crowding_score_kill=10.0,
    )


def test_kraken_live_readonly_preflight_passes_without_credentials():
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        execution=ExecutionSettings(mode="live_readonly", provider_id="kraken_derivatives"),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=FakeKrakenConnector())
    ok, reason = svc.preflight()
    assert ok is True
    assert reason == "readonly"


def test_kraken_live_testnet_is_fail_closed_until_trading_impl(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            provider_id="kraken_derivatives",
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=FakeKrakenConnector())
    ok, reason = svc.preflight()
    assert ok is False
    assert reason == "kraken_live_trading_not_implemented"


def test_kraken_readonly_preview_uses_connector_book():
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        execution=ExecutionSettings(mode="live_readonly", provider_id="kraken_derivatives"),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=FakeKrakenConnector())
    out = svc.execute_readonly(OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=10.0, why={}))
    assert out.status == "readonly_preview"
    assert out.order is not None
    assert out.order["book"]["bidPrice"] == "100"


def test_kraken_live_preflight_passes_when_connector_supports_trading(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode="live_testnet",
            provider_id="kraken_derivatives",
            maker_timeout_s=0,
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    ok, reason = svc.preflight()
    assert ok is True
    assert reason == "ok"


def test_kraken_rate_limit_storm_triggers_kill(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.fail_with_rate_limit = True
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives", maker_timeout_s=0),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    intent = OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=10.0, why={})
    last = None
    for _ in range(5):
        last = svc.execute_intent(intent)
    assert last is not None
    assert last.status == "killed"
    assert last.reason == "rate_limit_storm"
    assert svc.killed is True
    assert svc.safe_mode is True


def test_kraken_reconcile_and_flatten_mismatch(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake.positions = [{"symbol": "PI_XBTUSD", "positionAmt": "1.0", "markPrice": "100.0"}]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives", maker_timeout_s=0),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    ok, _ = svc.reconcile_live_state(internal_exposure=1.0)
    assert ok is False
    assert svc.safe_mode is True
    assert svc.killed is True

    calls = {"n": 0}

    def _position_risk(symbol=None):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"symbol": "PI_XBTUSD", "positionAmt": "1.0", "markPrice": "100.0"}]
        return []

    fake.position_risk = _position_risk
    ok2, reason2 = svc.reconcile_and_flatten_on_mismatch(internal_exposure=1.0, max_flatten_attempts=2)
    assert ok2 is False
    assert "flattened" in reason2


def test_kraken_flatten_cancels_open_orders_best_effort(monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")
    fake = FakeKrakenConnector()
    fake.supports_live_trading = True
    fake._open_orders = [{"symbol": "PI_XBTUSD", "clientOrderId": "abc"}]
    s = RobotSettings(
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_derivatives"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    svc = LiveKrakenService(s, run_id="r1", connector=fake)
    closed, reason = svc.flatten_all_positions()
    assert closed is True
    assert reason == "flat"
    assert fake.cancel_calls >= 1
