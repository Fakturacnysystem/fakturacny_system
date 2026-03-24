import pytest

from autonomous_investment_robot.config.settings import (
    DoctrineSettings,
    ExecutionSettings,
    HarmonySettings,
    LiveUnlockSettings,
    MarginSettings,
    MarketWatchSettings,
    MonitoringSettings,
    RiskLimits,
    RobotSettings,
    RolloutStage,
    SafetySettings,
    StorageSettings,
    TCOSettings,
)
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


def _limits() -> RiskLimits:
    return RiskLimits(
        max_daily_loss_pct=5.0,
        max_weekly_loss_pct=10.0,
        max_drawdown_pct=10.0,
        max_position_notional=1000.0,
        max_exposure_notional=5000.0,
        max_symbol_exposure_notional=3000.0,
        max_cluster_exposure_notional=4000.0,
        max_orders_per_min=5,
        leverage=0,
        stress_loss_limit_pct=5.0,
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


def test_execution_service_builds_passive_plan_when_market_quality_is_good():
    svc = ExecutionService(ExecutionSettings())
    intent = OrderIntent(symbol="BTCUSDT", side="buy", target_notional=100.0, why={})
    plan = svc.build_execution_plan(intent, depth_notional=100000.0, spread_bps=4.0, regime="RANGE", liquidity_regime="GOOD")
    assert plan.passive is True
    assert plan.order_style == "limit"
    assert plan.child_orders >= 1


def test_execution_service_blocks_open_below_venue_min_notional():
    svc = ExecutionService(ExecutionSettings(provider_id="binance_um_perps"))
    intent = OrderIntent(symbol="BTCUSDT", side="buy", target_notional=1.0, why={})

    plan = svc.build_execution_plan(intent, depth_notional=100000.0, spread_bps=2.0, regime="RANGE", liquidity_regime="GOOD")

    assert plan.target_notional == 0.0
    assert plan.reasons["constraint_adjustment"]["constraints_blocked"] is True


def test_execution_service_blocks_open_when_decision_doctrine_disallows_action():
    svc = ExecutionService(ExecutionSettings(provider_id="binance_um_perps"))
    intent = OrderIntent(
        symbol="BTCUSDT",
        side="buy",
        target_notional=100.0,
        why={"decision_doctrine": {"recommended_action": "no_trade", "size_multiplier": 0.0}},
    )

    plan = svc.build_execution_plan(intent, depth_notional=100000.0, spread_bps=2.0, regime="RANGE", liquidity_regime="GOOD")

    assert plan.target_notional == 0.0
    assert plan.reasons["global_execution_adjustments"]["hard_block"] is True
    assert plan.reasons["decision_doctrine"]["recommended_action"] == "no_trade"


def test_execution_service_uses_decision_doctrine_for_probe_style_and_size():
    svc = ExecutionService(ExecutionSettings(provider_id="binance_um_perps"))
    intent = OrderIntent(
        symbol="BTCUSDT",
        side="buy",
        target_notional=100.0,
        why={
            "decision_doctrine": {
                "recommended_action": "probe",
                "size_multiplier": 0.25,
                "uncertainty_pressure": 0.6,
                "partial_truth_penalty": 0.4,
                "execution_survivability_score": 0.45,
                "robustness_score": 0.5,
            },
            "market_integrity": {"action": "degrade"},
        },
    )

    plan = svc.build_execution_plan(intent, depth_notional=100000.0, spread_bps=2.0, regime="RANGE", liquidity_regime="GOOD")

    assert 0.0 < plan.target_notional <= 25.0
    assert plan.passive is True
    assert plan.order_style == "limit"
    assert plan.child_orders == 1
    assert plan.reasons["global_execution_adjustments"]["doctrine_action"] == "probe"


def test_execution_service_respects_mastermind_probe_style_and_size():
    svc = ExecutionService(ExecutionSettings(provider_id="binance_um_perps"))
    intent = OrderIntent(
        symbol="BTCUSDT",
        side="buy",
        target_notional=100.0,
        why={
            "decision_doctrine": {"recommended_action": "continue", "size_multiplier": 1.0},
            "mastermind": {
                "decision": "PROBE",
                "size_multiplier": 0.2,
                "execution_style_bias": "passive_limit",
            },
        },
    )

    plan = svc.build_execution_plan(intent, depth_notional=100000.0, spread_bps=2.0, regime="RANGE", liquidity_regime="GOOD")

    assert 0.0 < plan.target_notional <= 20.0
    assert plan.passive is True
    assert plan.order_style == "limit"
    assert plan.reasons["global_execution_adjustments"]["mastermind_action"] == "probe"


def test_execution_service_uses_doctrine_context_to_make_forced_exit_more_aggressive():
    svc = ExecutionService(ExecutionSettings(provider_id="binance_um_perps"))
    intent = OrderIntent(
        symbol="BTCUSDT",
        side="sell",
        target_notional=100.0,
        why={
            "decision_doctrine": {
                "recommended_action": "no_trade",
                "size_multiplier": 1.0,
                "partial_truth_penalty": 0.8,
            },
            "market_integrity": {"action": "flatten_only"},
            "human_escalation": {"action": "flatten_only"},
        },
    )

    plan = svc.build_exit_plan(
        intent,
        depth_notional=100000.0,
        spread_bps=2.0,
        regime="RANGE",
        liquidity_regime="GOOD",
        execution_style="passive_limit",
    )

    assert plan.reduce_only is True
    assert plan.order_style == "marketable_limit"
    assert plan.child_orders == 1
    assert plan.reasons["global_execution_adjustments"]["preferred_exit_style"] == "marketable_limit"


def test_execution_service_exposes_provider_capability_matrix():
    svc = ExecutionService(ExecutionSettings(provider_id="kraken_derivatives"))

    matrix = svc.provider_capability_matrix()

    assert matrix.provider_id == "kraken_derivatives"
    assert matrix.lifecycle_completeness == "strong_without_replace"
    assert matrix.replace_supported is False


def test_execution_service_supports_kraken_spot_provider_defaults():
    svc = ExecutionService(ExecutionSettings(provider_id="kraken_spot"))

    constraints = svc.venue_constraints("BTC/USD")
    matrix = svc.provider_capability_matrix()

    assert constraints.provider_id == "kraken_spot"
    assert constraints.min_notional > 0.0
    assert matrix.provider_id == "kraken_spot"
    assert matrix.realized_pnl_truth_support == "spot_trade_history_fifo_authoritative_when_balances_match"


def test_execution_service_fails_closed_on_unsupported_provider():
    svc = ExecutionService(ExecutionSettings(provider_id="coinbase_spot"))

    with pytest.raises(ValueError, match="unsupported_provider:coinbase_spot"):
        svc.venue_constraints("BTC/EUR")

    with pytest.raises(ValueError, match="unsupported_provider:coinbase_spot"):
        svc.provider_capability_matrix()


def test_risk_engine_sets_kill_switch_mode_on_balance_state_failure():
    risk = RiskEngineService(_limits(), safe_mode=False)
    decision = risk.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        current_exposure=0.0,
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        data_lag_seconds=0.0,
        spread_bps=1.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.0,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
        balance_state_ok=False,
    )
    assert decision.allowed is False
    assert decision.reason == "balance_state_kill"
    assert decision.details["risk_mode"] == "kill-switch"


def test_risk_engine_rejects_when_decision_doctrine_truth_is_weak():
    risk = RiskEngineService(_limits(), safe_mode=False)
    decision = risk.evaluate(
        OrderIntent("BTCUSDT", "buy", 100.0, {}),
        current_exposure=0.0,
        drawdown_pct=0.0,
        daily_loss_pct=0.0,
        data_lag_seconds=0.0,
        spread_bps=1.0,
        depth_notional=1000.0,
        reconciliation_ok=True,
        funding_paid_pct=0.0,
        oi_spike_pct=0.0,
        liquidation_spike=0.0,
        divergence_bps=0.0,
        margin_buffer=3.0,
        balance_state_ok=True,
        doctrine_truth_strength=0.2,
    )
    assert decision.allowed is False
    assert decision.reason == "decision_doctrine_truth_weak"
    assert decision.details["risk_mode"] == "flatten-only"


def test_robot_settings_margin_is_fail_closed_in_non_paper_modes(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    with pytest.raises(ValueError, match="Margin live trading blocked"):
        RobotSettings(
            provider_whitelist=["binance_um_perps"],
            execution=ExecutionSettings(mode="live_testnet"),
            risk=_limits(),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
            margin=MarginSettings(enabled=True, max_leverage=2),
        )


def test_robot_settings_rollout_stage_and_live_gate_manifest(monkeypatch):
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    settings = RobotSettings(
        provider_whitelist=["kraken_spot"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live_testnet", provider_id="kraken_spot"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        doctrine=DoctrineSettings(
            target_provider="kraken_spot",
            product_target="spot",
            long_only=True,
            never_open_new_short_exposure=True,
            minimum_sell_net_profit_bps=120.0,
            enforce_cost_basis_sell_block=True,
            enforce_net_profit_sell_block=True,
            block_non_reduce_only_sells=True,
        ),
        harmony=HarmonySettings(enabled=True, default_order_cadence_s=5.0),
        market_watch=MarketWatchSettings(enabled=True),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        storage=StorageSettings(run_dir="runs/canary_testnet"),
    )

    assert settings.rollout_stage() == RolloutStage.TINY_LIVE
    live_gate = settings.live_gate_status()
    assert live_gate["rollout_stage"] == "tiny_live"
    assert live_gate["provider_whitelisted"] is True
    assert live_gate["live_ordering_enabled"] is True
    assert live_gate["doctrine_launch_safe"] is True

    manifest = settings.config_manifest()
    assert manifest["schema_version"] == settings.config_schema_version
    assert manifest["rollout_stage"] == "tiny_live"
    assert manifest["live_gate_status"]["runtime_mode"] == "live_testnet"
    assert manifest["live_gate_status"]["provider_supported"] is True


def test_robot_settings_rejects_unsupported_live_provider():
    with pytest.raises(ValueError, match="Unsupported execution provider: coinbase_spot"):
        RobotSettings(
            provider_whitelist=["coinbase_spot"],
            execution=ExecutionSettings(mode="live_testnet", provider_id="coinbase_spot"),
            safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
            risk=_limits(),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_robot_settings_blocks_non_spot_order_capable_live_provider(monkeypatch):
    monkeypatch.setenv("EXCHANGE_API_KEY", "k")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "s")
    with pytest.raises(ValueError, match="unsupported_doctrine_target_use_kraken_spot"):
        RobotSettings(
            provider_whitelist=["binance_um_perps"],
            execution=ExecutionSettings(mode="live", provider_id="binance_um_perps"),
            safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
            risk=_limits(),
            tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        )


def test_robot_settings_config_hash_changes_when_manifest_changes(monkeypatch):
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "k")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "s")
    base = RobotSettings(
        provider_whitelist=["kraken_spot"],
        canary_mode=True,
        execution=ExecutionSettings(mode="live", provider_id="kraken_spot"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False)),
        doctrine=DoctrineSettings(
            target_provider="kraken_spot",
            product_target="spot",
            long_only=True,
            never_open_new_short_exposure=True,
            minimum_sell_net_profit_bps=120.0,
            enforce_cost_basis_sell_block=True,
            enforce_net_profit_sell_block=True,
            block_non_reduce_only_sells=True,
        ),
        harmony=HarmonySettings(enabled=True, default_order_cadence_s=5.0),
        market_watch=MarketWatchSettings(enabled=True),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        storage=StorageSettings(run_dir="runs/canary_live"),
    )
    changed = RobotSettings(
        provider_whitelist=["kraken_spot"],
        canary_mode=False,
        execution=ExecutionSettings(mode="live", provider_id="kraken_spot"),
        safety=SafetySettings(live_unlock=LiveUnlockSettings(enable_live_trading=True, ack_i_understand_risks=True, require_testnet_passed=False, canary_required_before_full=False)),
        doctrine=DoctrineSettings(
            target_provider="kraken_spot",
            product_target="spot",
            long_only=True,
            never_open_new_short_exposure=True,
            minimum_sell_net_profit_bps=120.0,
            enforce_cost_basis_sell_block=True,
            enforce_net_profit_sell_block=True,
            block_non_reduce_only_sells=True,
        ),
        harmony=HarmonySettings(enabled=True, default_order_cadence_s=10.0),
        market_watch=MarketWatchSettings(enabled=True),
        risk=_limits(),
        tco=TCOSettings(max_total_cost_bps=10.0, max_impact_bps=10.0),
        storage=StorageSettings(run_dir="runs/prod_live"),
        monitoring=MonitoringSettings(loop_latency_warn_ms=1500.0),
    )

    assert base.rollout_stage() == RolloutStage.CANARY_LIVE
    assert changed.rollout_stage() == RolloutStage.NORMAL_LIVE
    assert base.config_hash() != changed.config_hash()
