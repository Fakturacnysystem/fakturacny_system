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

    @property
    def has_credentials(self):
        return self._has_credentials

    def verify_live_permissions(self):
        return True, "ok"

    def book_ticker(self, symbol):
        return {"bidPrice": "100", "askPrice": "101", "bidQty": "1", "askQty": "1", "symbol": symbol}


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

