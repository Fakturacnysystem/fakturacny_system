from __future__ import annotations

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
    @property
    def has_credentials(self):
        return True

    def book_ticker(self, symbol):  # noqa: ARG002
        return {"bidPrice": "100.0", "askPrice": "100.1", "bidQty": "10", "askQty": "10"}

    def open_orders(self, symbol=None):  # noqa: ARG002
        return []

    def position_risk(self, symbol=None):  # noqa: ARG002
        return []


def _limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_pct=1.0,
        max_weekly_loss_pct=2.0,
        max_drawdown_pct=2.0,
        max_position_notional=100.0,
        max_exposure_notional=100.0,
        max_symbol_exposure_notional=100.0,
        max_cluster_exposure_notional=100.0,
        max_orders_per_min=5,
        leverage=0,
        target_portfolio_vol=0.05,
        cvar_limit_pct=1.0,
        stress_loss_limit_pct=2.0,
        max_spread_bps=15.0,
        min_depth_notional=1000.0,
        stale_data_seconds=10.0,
        min_margin_buffer=2.0,
        max_funding_cost_per_day=0.0,
        max_oi_spike_pct=0.0,
        max_liquidation_spike=0.0,
        divergence_threshold_bps=10.0,
        crowding_score_kill=12.0,
    )


def _settings(mode: str = "live_testnet") -> RobotSettings:
    return RobotSettings(
        provider_whitelist=["binance_um_perps"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode=mode,
            provider_id="binance_um_perps",
            binance=BinanceExecutionSettings(allow_unknown_permissions=True),
        ),
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(
                enable_live_trading=True,
                ack_i_understand_risks=True,
                require_testnet_passed=False,
            )
        ),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")


def test_binance_preflight_is_blocked_for_order_capable_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    svc = LiveBinanceService(_settings("live_testnet"), run_id="r1", connector=FakeConnector())

    ok, reason = svc.preflight()

    assert ok is False
    assert reason == "unsupported_doctrine_target_use_kraken_spot"


def test_binance_execute_intent_is_killed_for_order_capable_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    svc = LiveBinanceService(_settings("live_testnet"), run_id="r1", connector=FakeConnector())

    out = svc.execute_intent(OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={}))

    assert out.status == "killed"
    assert out.reason == "unsupported_doctrine_target_use_kraken_spot"


def test_binance_flatten_is_blocked_for_order_capable_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    svc = LiveBinanceService(_settings("live_testnet"), run_id="r1", connector=FakeConnector())

    closed, reason = svc.flatten_all_positions()

    assert closed is False
    assert reason == "unsupported_doctrine_target_use_kraken_spot"


def test_binance_readonly_preview_remains_available(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    svc = LiveBinanceService(_settings("live_readonly"), run_id="r1", connector=FakeConnector())

    ok, reason = svc.preflight()
    out = svc.execute_readonly(OrderIntent(symbol="BTCUSDT", side="buy", target_notional=10.0, why={}))

    assert ok is True
    assert reason == "readonly"
    assert out.status == "readonly_preview"
    assert out.order["symbol"] == "BTCUSDT"


def test_binance_capability_evidence_still_tracks_runtime_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    svc = LiveBinanceService(_settings("live_readonly"), run_id="r1", connector=FakeConnector())

    svc.capture_market_integrity_evidence(
        {"bidPrice": "100.0", "askPrice": "100.1", "bidQty": "5", "askQty": "5", "sequence_ok": False},
        1700000000.0,
    )
    payload = svc.capability_evidence(now_dt=1700000001.0)

    assert payload["public_market_data_connected"] is True
    assert payload["sequence_ok"] is False
    assert payload["supports_live_trading"] is True
