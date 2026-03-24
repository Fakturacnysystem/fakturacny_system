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
