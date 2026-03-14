from autonomous_investment_robot.config.settings import ExecutionSettings, RobotSettings
from autonomous_investment_robot.services.ops.harmony import HarmonyConfigResolver


def test_harmony_default_profit_floor_remains_30_bps() -> None:
    settings = RobotSettings()
    resolved = HarmonyConfigResolver().resolve(
        settings,
        {
            "AUTONOMOUS_PROFIT_TARGET_NET": "0.0",
            "AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS": "0",
            "AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS": "0",
        },
        exchange_min_quote_fallback=2.0,
        dry_run=True,
    )
    assert resolved.sell_min_profit_bps >= 30.0


def test_harmony_allows_explicit_33bps_hard_floor_override() -> None:
    settings = RobotSettings()
    resolved = HarmonyConfigResolver().resolve(
        settings,
        {
            "AUTONOMOUS_SELL_HARD_MIN_PROFIT_BPS": "33",
            "AUTONOMOUS_SPOT_SELL_HARD_FLOOR_BPS": "33",
            "AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS": "33",
            "AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS": "33",
            "AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS": "33",
            "AUTONOMOUS_PROFIT_TARGET_NET": "0.0033",
        },
        exchange_min_quote_fallback=2.0,
        dry_run=True,
    )
    assert resolved.sell_min_profit_bps == 33.0
    assert resolved.sell_target_profit_bps == 33.0


def test_harmony_never_goes_below_modeled_cost_floor() -> None:
    settings = RobotSettings(
        execution=ExecutionSettings(
            fee_bps=30.0,
            slippage_bps=20.0,
        )
    )
    resolved = HarmonyConfigResolver().resolve(
        settings,
        {
            "AUTONOMOUS_SELL_HARD_MIN_PROFIT_BPS": "33",
            "AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS": "33",
            "AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS": "33",
            "AUTONOMOUS_PROFIT_TARGET_NET": "0.0033",
        },
        exchange_min_quote_fallback=2.0,
        dry_run=True,
    )
    # Modeled floor = 2 * fee + 2 * slippage.
    assert resolved.sell_min_profit_bps >= 100.0


def test_harmony_resolved_config_fingerprint_is_deterministic() -> None:
    settings = RobotSettings()
    env = {
        "AUTONOMOUS_SELL_HARD_MIN_PROFIT_BPS": "33",
        "AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS": "33",
        "AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS": "33",
        "AUTONOMOUS_PROFIT_TARGET_NET": "0.0033",
    }
    resolver = HarmonyConfigResolver()
    first = resolver.resolve(
        settings,
        env,
        exchange_min_quote_fallback=2.0,
        dry_run=True,
    )
    second = resolver.resolve(
        settings,
        env,
        exchange_min_quote_fallback=2.0,
        dry_run=True,
    )
    assert first.resolved_config_fingerprint
    assert first.resolved_config_fingerprint == second.resolved_config_fingerprint
