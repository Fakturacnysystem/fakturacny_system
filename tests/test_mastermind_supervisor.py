from autonomous_investment_robot.services.mastermind.service import MastermindSupervisor
from autonomous_investment_robot.services.ops.harmony import ResolvedHarmonyConfig


def _harmony_with_sell_floor(sell_min_profit_bps: float) -> ResolvedHarmonyConfig:
    return ResolvedHarmonyConfig(
        order_cadence_s=9.0,
        guards_mode="fatal_only",
        user_min_order_quote=0.25,
        exchange_min_order_quote=0.25,
        effective_min_order_quote=0.25,
        sell_min_profit_bps=sell_min_profit_bps,
        sell_target_profit_bps=sell_min_profit_bps,
        tp_only_mode=True,
        max_orders_per_min=60,
        market_watch_every_s=10.0,
        market_watch_max_calls_per_min=60,
        blackout_enabled=True,
        blackout_windows_present=False,
        spread_spike_enabled=True,
        spread_spike_mult=2.5,
        spread_spike_min_bps=8.0,
        spread_spike_edge_add_bps=6.0,
        spread_spike_hold_s=45.0,
        liquidity_map_enabled=True,
    )


def test_preflight_uses_default_30_hard_floor(tmp_path) -> None:
    sup = MastermindSupervisor(str(tmp_path))
    state = sup.preflight(_harmony_with_sell_floor(20.0))
    assert state.ok is False
    assert state.reason == "sell_min_profit_bps_below_hard_floor"
    assert state.guardrails.get("hard_floor_bps") == 30.0


def test_preflight_allows_configurable_hard_floor_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_SELL_HARD_MIN_PROFIT_BPS", "33")
    sup = MastermindSupervisor(str(tmp_path))
    state = sup.preflight(_harmony_with_sell_floor(33.0))
    assert state.ok is True
    assert state.reason == "ok"
    assert state.guardrails.get("hard_floor_bps") == 33.0


def test_runtime_single_rate_limit_event_does_not_pause_buy(tmp_path) -> None:
    sup = MastermindSupervisor(str(tmp_path))
    state = sup.observe_runtime(
        reject_rate=1.0,
        rate_limit_events=1.0,
        insufficient_balance_events=0.0,
        no_intent_events=0.0,
        sell_breach_detected=False,
        base_max_orders_per_min=10,
        base_market_watch_budget=60,
    )
    assert state.reason == "ok"
    assert state.pause_buy is False
    assert state.max_orders_per_min_override is None


def test_runtime_rate_stress_requires_multi_event_evidence(tmp_path) -> None:
    sup = MastermindSupervisor(str(tmp_path))
    state = sup.observe_runtime(
        reject_rate=0.85,
        rate_limit_events=4.0,
        insufficient_balance_events=0.0,
        no_intent_events=0.0,
        sell_breach_detected=False,
        base_max_orders_per_min=10,
        base_market_watch_budget=60,
    )
    assert state.reason == "rate_stress"
    assert state.pause_buy is True
    assert state.max_orders_per_min_override == 5


def test_runtime_rate_limit_noise_without_rejects_does_not_pause_buy(tmp_path) -> None:
    sup = MastermindSupervisor(str(tmp_path))
    state = sup.observe_runtime(
        reject_rate=0.0,
        rate_limit_events=6.0,
        insufficient_balance_events=0.0,
        no_intent_events=0.0,
        sell_breach_detected=False,
        base_max_orders_per_min=10,
        base_market_watch_budget=60,
    )
    assert state.reason == "ok"
    assert state.pause_buy is False
    assert state.max_orders_per_min_override is None


def test_runtime_insufficient_balance_is_warn_only_in_fatal_only_mode(tmp_path) -> None:
    sup = MastermindSupervisor(str(tmp_path))
    state = sup.observe_runtime(
        reject_rate=0.0,
        rate_limit_events=0.0,
        insufficient_balance_events=4.0,
        no_intent_events=0.0,
        sell_breach_detected=False,
        base_max_orders_per_min=10,
        base_market_watch_budget=60,
        guards_mode="fatal_only",
    )
    assert state.reason == "insufficient_balance_warn"
    assert state.pause_buy is False
    assert state.max_orders_per_min_override is None
    assert state.market_watch_max_calls_per_min_override is None


def test_runtime_rate_stress_is_warn_only_in_fatal_only_mode(tmp_path) -> None:
    sup = MastermindSupervisor(str(tmp_path))
    state = sup.observe_runtime(
        reject_rate=0.9,
        rate_limit_events=6.0,
        insufficient_balance_events=0.0,
        no_intent_events=0.0,
        sell_breach_detected=False,
        base_max_orders_per_min=10,
        base_market_watch_budget=60,
        guards_mode="fatal_only",
    )
    assert state.reason == "rate_stress_warn"
    assert state.pause_buy is False
    assert state.max_orders_per_min_override is None
    assert state.market_watch_max_calls_per_min_override is None
