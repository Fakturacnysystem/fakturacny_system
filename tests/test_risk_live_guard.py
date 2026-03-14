import pytest

from autonomous_investment_robot.config.settings import ExecutionSettings, LiveUnlockSettings, RiskLimits, RobotSettings, SafetySettings, TCOSettings
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


def _complete_limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_pct=5.0,
        max_drawdown_pct=10.0,
        max_position_notional=1000.0,
        max_exposure_notional=2000.0,
        max_orders_per_min=10,
        leverage=0,
        target_portfolio_vol=0.2,
        cvar_limit_pct=4.0,
        max_spread_bps=20.0,
        min_depth_notional=100.0,
        stale_data_seconds=60.0,
        min_margin_buffer=2.0,
        max_funding_cost_per_day=1.0,
        max_oi_spike_pct=3.0,
        max_liquidation_spike=100000.0,
        divergence_threshold_bps=30.0,
        crowding_score_kill=25.0,
    )


def test_live_mode_rejected_without_double_unlock():
    with pytest.raises(ValueError):
        RobotSettings(
            execution=ExecutionSettings(mode="live_testnet"),
            provider_whitelist=["binance_um_perps"],
            safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=False, require_testnet_passed=False)),
            risk=_complete_limits(),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_live_mode_rejected_without_limits_even_if_unlocked():
    with pytest.raises(ValueError):
        RobotSettings(
            execution=ExecutionSettings(mode="live_testnet"),
            provider_whitelist=["binance_um_perps"],
            safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_live_mode_rejected_without_canary():
    with pytest.raises(ValueError):
        RobotSettings(
            execution=ExecutionSettings(mode="live"),
            provider_whitelist=["binance_um_perps"],
            safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False, canary_required_before_full=True)),
            canary_mode=False,
            risk=_complete_limits(),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_live_mode_can_initialize_only_with_limits_and_double_unlock(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    s = RobotSettings(
        execution=ExecutionSettings(mode="live_testnet"),
        provider_whitelist=["binance_um_perps"],
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        canary_mode=True,
        risk=_complete_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    assert s.execution.mode == "live_testnet"


def test_live_mode_rejected_without_manual_live_gate(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_LIVE_GO", "0")
    with pytest.raises(ValueError) as exc:
        RobotSettings(
            execution=ExecutionSettings(mode="live"),
            provider_whitelist=["binance_um_perps"],
            safety=SafetySettings(
                live_unlock=LiveUnlockSettings(
                    enable_live_trading=True,
                    ack_i_understand_risks=True,
                    require_testnet_passed=False,
                    canary_required_before_full=False,
                )
            ),
            canary_mode=True,
            risk=_complete_limits(),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )
    text = str(exc.value)
    assert "AUTONOMOUS_LIVE_GO" in text


def test_live_mode_accepts_manual_live_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    monkeypatch.setenv("AUTONOMOUS_LIVE_GO", "1")
    confirmation = tmp_path / "live_confirmation.txt"
    confirmation.write_text("manual operator confirmation", encoding="utf-8")
    monkeypatch.setenv("AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE", str(confirmation))
    settings = RobotSettings(
        execution=ExecutionSettings(mode="live"),
        provider_whitelist=["binance_um_perps"],
        safety=SafetySettings(
            live_unlock=LiveUnlockSettings(
                enable_live_trading=True,
                ack_i_understand_risks=True,
                require_testnet_passed=False,
                canary_required_before_full=False,
            )
        ),
        canary_mode=True,
        risk=_complete_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
    )
    assert settings.execution.mode == "live"


def _risk_intent(side: str = "buy", notional: float = 100.0) -> OrderIntent:
    return OrderIntent(symbol="XBTUSD", side=side, target_notional=notional, why={})


def _risk_decision(risk: RiskEngineService, *, side: str, is_reduce_only: bool):
    return risk.evaluate(
        intent=_risk_intent(side=side),
        current_exposure=0.0,
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        data_lag_seconds=0.0,
        spread_bps=5.0,
        depth_notional=10_000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.0,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=999.0,
        funding_rate_abs=0.0,
        weekly_loss_pct=0.0,
        symbol_exposure=0.0,
        cluster_exposure=0.0,
        market_regime="RANGE",
        liquidity_regime="GOOD",
        is_reduce_only=is_reduce_only,
        side=side,
    )


def test_risk_engine_shield_observe_only_blocks_new_entries() -> None:
    risk = RiskEngineService(_complete_limits(), safe_mode=False)
    risk.apply_shield_telemetry(mode="observe_only", reason_codes=["confidence_collapse"], source="unit_test")
    decision = _risk_decision(risk, side="buy", is_reduce_only=False)
    assert decision.allowed is False
    assert decision.reason == "shield_observe_only"
    assert decision.details.get("shield_mode") == "observe_only"


def test_risk_engine_shield_hard_stop_non_bypassable_but_reduce_allowed() -> None:
    risk = RiskEngineService(_complete_limits(), safe_mode=False)
    risk.apply_shield_telemetry(mode="hard_stop", reason_codes=["hard_safety_doctrine"], source="unit_test")
    blocked = _risk_decision(risk, side="buy", is_reduce_only=False)
    assert blocked.allowed is False
    assert blocked.reason == "shield_hard_stop"
    assert blocked.flatten is True
    reduce_ok = _risk_decision(risk, side="sell", is_reduce_only=True)
    assert reduce_ok.allowed is True
    assert reduce_ok.reason == "shield_hard_stop_reduce_only"
