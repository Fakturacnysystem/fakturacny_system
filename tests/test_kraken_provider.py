from __future__ import annotations

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
    def __init__(self, *, has_credentials: bool = True):
        self._has_credentials = has_credentials

    @property
    def has_credentials(self):
        return self._has_credentials

    def book_ticker(self, symbol):  # noqa: ARG002
        return {"bidPrice": "100", "askPrice": "101", "bidQty": "1", "askQty": "1", "symbol": symbol}

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
        provider_whitelist=["kraken_derivatives"],
        canary_mode=True,
        execution=ExecutionSettings(
            mode=mode,
            provider_id="kraken_derivatives",
            kraken=KrakenExecutionSettings(allow_unknown_permissions=True),
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
        universe=["PI_XBTUSD"],
    )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAKEN_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_API_SECRET", "s")


def test_kraken_live_readonly_preflight_passes_without_credentials() -> None:
    svc = LiveKrakenService(_settings("live_readonly"), run_id="r1", connector=FakeKrakenConnector(has_credentials=False))

    ok, reason = svc.preflight()

    assert ok is True
    assert reason == "readonly"


def test_kraken_order_capable_preflight_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    svc = LiveKrakenService(_settings("live_testnet"), run_id="r1", connector=FakeKrakenConnector())

    ok, reason = svc.preflight()

    assert ok is False
    assert reason == "unsupported_doctrine_target_use_kraken_spot"


def test_kraken_execute_intent_is_killed_for_order_capable_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    svc = LiveKrakenService(_settings("live_testnet"), run_id="r1", connector=FakeKrakenConnector())

    out = svc.execute_intent(OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=10.0, why={}))

    assert out.status == "killed"
    assert out.reason == "unsupported_doctrine_target_use_kraken_spot"


def test_kraken_flatten_is_blocked_for_order_capable_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    svc = LiveKrakenService(_settings("live_testnet"), run_id="r1", connector=FakeKrakenConnector())

    closed, reason = svc.flatten_all_positions()

    assert closed is False
    assert reason == "unsupported_doctrine_target_use_kraken_spot"


def test_kraken_readonly_preview_uses_connector_book() -> None:
    svc = LiveKrakenService(_settings("live_readonly"), run_id="r1", connector=FakeKrakenConnector())

    out = svc.execute_readonly(OrderIntent(symbol="PI_XBTUSD", side="buy", target_notional=10.0, why={}))

    assert out.status == "readonly_preview"
    assert out.order["book"]["symbol"] == "PI_XBTUSD"


def test_kraken_capability_evidence_tracks_runtime_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    svc = LiveKrakenService(_settings("live_readonly"), run_id="r1", connector=FakeKrakenConnector())

    svc.capture_market_integrity_evidence(
        {"bidPrice": "100", "askPrice": "101", "bidQty": "1", "askQty": "1", "checksum_ok": False},
        1700000000.0,
    )
    payload = svc.capability_evidence(now_dt=1700000001.0)

    assert payload["public_market_data_connected"] is True
    assert payload["checksum_ok"] is False
    assert payload["replace_support_evidence"] == "dynamic"
