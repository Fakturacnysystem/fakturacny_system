from datetime import datetime, timedelta, timezone

from autonomous_investment_robot.core.contracts import ExecutionQualityForecast
from autonomous_investment_robot.services.observability_service.service import ObservabilityService
from autonomous_investment_robot.services.ops.service import OpsService
from autonomous_investment_robot.services.reporting_service.service import ReportingCoordinator
from autonomous_investment_robot.services.execution.service import Fill
from autonomous_investment_robot.services.inventory_service.service import InventoryService
from autonomous_investment_robot.services.profitability_service.service import ProfitabilityService


def test_inventory_service_tracks_lots_and_pressure():
    inventory = InventoryService()
    old_ts = datetime.now(timezone.utc) - timedelta(hours=18)
    inventory.update_from_fill(
        Fill("paper", "o1", "f1", "BTCUSDT", "buy", 100.0, 0.5, 0.5, 10, "filled"),
        ts=old_ts,
        expected_exit_cost_bps=4.0,
    )
    state = inventory.inventory_pressure(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        opportunity_cost_score=0.7,
        unrealized_pnl=-15.0,
        truth_pressure=0.4,
        execution_fragility=0.5,
    )
    assert state.gross_open_notional == 100.0
    assert state.oldest_age_seconds >= 18 * 3600
    assert state.stale_inventory_score > 0.35


def test_profitability_service_blocks_non_positive_round_trip_and_emits_release():
    inventory = InventoryService()
    ts = datetime.now(timezone.utc) - timedelta(hours=24)
    inventory.update_from_fill(
        Fill("paper", "o1", "f1", "BTCUSDT", "buy", 100.0, 0.5, 0.5, 10, "filled"),
        ts=ts,
    )
    inventory_state = inventory.inventory_pressure(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        opportunity_cost_score=0.8,
        unrealized_pnl=-10.0,
        execution_fragility=0.6,
    )
    reserve_state = inventory.reserve_state(
        ts=datetime.now(timezone.utc),
        exchange_balance=100.0,
        local_cash_delta=0.0,
        gross_exposure_notional=95.0,
        minimum_reserve_pct=0.2,
        capital_floor=100.0,
    )
    svc = ProfitabilityService(base_safety_buffer_bps=1.0, min_free_quote_reserve_pct=0.2)
    floor, release, round_trip = svc.evaluate_open(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        target_notional=100.0,
        expected_edge_bps=2.0,
        fee_bps=2.0,
        slippage_bps=2.0,
        spread_bps=3.0,
        depth_notional=500.0,
        execution_quality=ExecutionQualityForecast("BTCUSDT", datetime.now(timezone.utc), 0.4, 250, 2.0, 0.4, False, {}),
        inventory_state=inventory_state,
        reserve_state=reserve_state,
    )
    assert floor.capital_release_allowed is True
    assert release.allowed is True
    assert round_trip.action in {"wait", "no_trade", "trade_smaller"}
    assert round_trip.net_edge_bps <= 0.0 or reserve_state.reserve_breached


def test_profitability_service_builds_exit_intent_for_stale_inventory():
    inventory = InventoryService()
    ts = datetime.now(timezone.utc) - timedelta(hours=24)
    inventory.update_from_fill(
        Fill("paper", "o1", "f1", "BTCUSDT", "buy", 120.0, 0.5, 0.5, 10, "filled"),
        ts=ts,
    )
    inventory_state = inventory.inventory_pressure(symbol="BTCUSDT", ts=datetime.now(timezone.utc), opportunity_cost_score=0.8)
    reserve_state = inventory.reserve_state(
        ts=datetime.now(timezone.utc),
        exchange_balance=100.0,
        local_cash_delta=0.0,
        gross_exposure_notional=95.0,
        minimum_reserve_pct=0.2,
        capital_floor=100.0,
    )
    svc = ProfitabilityService()
    release, exit_intent = svc.evaluate_exit(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        inventory_state=inventory_state,
        reserve_state=reserve_state,
        current_exposure=100.0,
    )
    assert release.allowed is True
    assert exit_intent is not None
    assert exit_intent.side == "sell"
    assert exit_intent.reduce_only is True


def test_profitability_service_marks_below_cost_basis_capital_release_explicitly():
    inventory = InventoryService()
    ts = datetime.now(timezone.utc) - timedelta(hours=24)
    inventory.update_from_fill(
        Fill("paper", "o1", "f1", "BTCUSDT", "buy", 120.0, 0.5, 0.5, 10, "filled"),
        ts=ts,
    )
    inventory_state = inventory.inventory_pressure(symbol="BTCUSDT", ts=datetime.now(timezone.utc), opportunity_cost_score=0.8)
    reserve_state = inventory.reserve_state(
        ts=datetime.now(timezone.utc),
        exchange_balance=100.0,
        local_cash_delta=0.0,
        gross_exposure_notional=95.0,
        minimum_reserve_pct=0.2,
        capital_floor=100.0,
    )
    svc = ProfitabilityService()
    release, exit_intent = svc.evaluate_exit(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        inventory_state=inventory_state,
        reserve_state=reserve_state,
        current_exposure=90.0,
    )

    assert release.allowed is True
    assert release.reason == "reserve_breach_below_cost_basis_capital_release"
    assert release.metadata["cost_basis_proxy_state"] == "below_cost_basis_proxy"
    assert exit_intent is not None
    assert exit_intent.metadata["capital_release_allowed"] is True


def test_profitability_service_marks_profit_lock_partial_exit_when_above_cost_basis():
    inventory = InventoryService()
    ts = datetime.now(timezone.utc) - timedelta(hours=24)
    inventory.update_from_fill(
        Fill("paper", "o1", "f1", "BTCUSDT", "buy", 120.0, 0.5, 0.5, 10, "filled"),
        ts=ts,
    )
    inventory_state = inventory.inventory_pressure(symbol="BTCUSDT", ts=datetime.now(timezone.utc), opportunity_cost_score=0.8)
    svc = ProfitabilityService()
    release, exit_intent = svc.evaluate_exit(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        inventory_state=inventory_state,
        reserve_state=None,
        current_exposure=135.0,
    )

    assert release.allowed is True
    assert release.reason == "profit_lock_partial_exit"
    assert "profit_locking" in release.reasons
    assert exit_intent is not None
    assert exit_intent.metadata["profit_locking"] is True


def test_profitability_service_emits_exit_path_comparison_and_reacceleration_hold_bias():
    inventory = InventoryService()
    ts = datetime.now(timezone.utc) - timedelta(hours=24)
    inventory.update_from_fill(
        Fill("paper", "o1", "f1", "BTCUSDT", "buy", 120.0, 0.5, 0.5, 10, "filled"),
        ts=ts,
    )
    inventory_state = inventory.inventory_pressure(symbol="BTCUSDT", ts=datetime.now(timezone.utc), opportunity_cost_score=0.8)
    svc = ProfitabilityService()
    release, exit_intent = svc.evaluate_exit(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        inventory_state=inventory_state,
        reserve_state=None,
        current_exposure=135.0,
        regime_label="RANGE",
        liquidity_regime="GOOD",
        execution_quality=ExecutionQualityForecast("BTCUSDT", datetime.now(timezone.utc), 0.8, 150, 1.0, 0.1, True, {}),
        synthetic_affect=type("Affect", (), {"stress": 0.1, "conviction": 0.85, "fear": 0.1})(),
        position_morph_plan=type("Morph", (), {"allow_runner": True, "runner_fraction": 0.2})(),
    )

    assert release.allowed is True
    assert exit_intent is not None
    assert exit_intent.metadata["requires_doctrine_sell_eligibility"] is True
    assert exit_intent.metadata["selected_exit_family"] in {
        "staged_partial_exit",
        "volatility_trailing",
        "reacceleration_hold",
        "time_decay_exit",
    }
    assert exit_intent.metadata["exit_path_comparison"]["families"]
    assert release.metadata["winner_monetization"]["state"] == exit_intent.metadata["selected_exit_family"]


def test_reporting_coordinator_surfaces_deadlock_and_stagnation_flags(tmp_path):
    coordinator = ReportingCoordinator(observability=ObservabilityService(str(tmp_path), OpsService(str(tmp_path))))

    payload = coordinator.report_profitability(
        symbol="BTCUSDT",
        profitability={
            "capital_release": {"allowed": True, "reason": "profit_lock_partial_exit", "reasons": ["stale_inventory", "profit_locking"]},
            "round_trip": {"action": "trade_now"},
        },
    )

    assert payload["quote_balance_deadlock"] is False
    assert payload["inventory_stagnation"] is True
    assert payload["profit_lock_candidate"] is True


def test_inventory_reserve_state_prefers_quote_asset_affordability_truth():
    reserve_state = InventoryService().reserve_state(
        ts=datetime.now(timezone.utc),
        exchange_balance=5000.0,
        local_cash_delta=0.0,
        gross_exposure_notional=0.0,
        minimum_reserve_pct=0.2,
        capital_floor=100.0,
        quote_asset="USD",
        quote_total_balance=20.0,
        quote_free_balance=15.9,
        quote_used_balance=4.1,
        required_quote_with_fee_buffer=12.05,
    )

    assert reserve_state.total_capital == 20.0
    assert reserve_state.free_quote == 15.9
    assert reserve_state.reserve_floor_quote == 4.0
    assert reserve_state.entry_buying_power_quote == 11.9
    assert reserve_state.required_quote_with_fee_buffer == 12.05
    assert reserve_state.metadata["affordability_source"] == "quote_asset_balance"
    assert reserve_state.metadata["reserve_policy_source"] == "policy_default"
    assert reserve_state.metadata["configured_minimum_reserve_pct"] == 0.2


def test_inventory_reserve_state_surfaces_override_policy_metadata():
    reserve_state = InventoryService().reserve_state(
        ts=datetime.now(timezone.utc),
        exchange_balance=5000.0,
        local_cash_delta=0.0,
        gross_exposure_notional=0.0,
        minimum_reserve_pct=0.0,
        capital_floor=100.0,
        quote_asset="EUR",
        quote_total_balance=20.0,
        quote_free_balance=19.0,
        quote_used_balance=1.0,
        reserve_policy_source="tiny_live_lifecycle_proof_override",
        configured_minimum_reserve_pct=0.55,
    )

    assert reserve_state.reserve_floor_quote == 0.0
    assert reserve_state.entry_buying_power_quote == 19.0
    assert reserve_state.metadata["reserve_policy_source"] == "tiny_live_lifecycle_proof_override"
    assert reserve_state.metadata["configured_minimum_reserve_pct"] == 0.55
