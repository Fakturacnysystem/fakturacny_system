from __future__ import annotations

from autonomous_investment_robot.core.orchestrator import _capital_unlock_sell_plan


def test_capital_unlock_sell_plan_allows_safe_candidate() -> None:
    plan = _capital_unlock_sell_plan(
        enabled=True,
        sell_profit_lock_require_cost_basis=True,
        bid_price=101.5,
        avg_entry_price=100.0,
        available_base_qty=1.2,
        min_unlock_notional_quote=15.0,
        shortfall_quote=40.0,
        shortfall_cover_ratio=1.05,
        required_exit_price=101.2,
    )
    assert plan["allowed"] is True
    assert float(plan["target_notional_quote"]) >= 40.0
    assert float(plan["required_exit_price"]) == 101.2


def test_capital_unlock_sell_plan_blocks_below_min_profit_floor() -> None:
    plan = _capital_unlock_sell_plan(
        enabled=True,
        sell_profit_lock_require_cost_basis=True,
        bid_price=100.5,
        avg_entry_price=100.0,
        available_base_qty=2.0,
        min_unlock_notional_quote=15.0,
        shortfall_quote=30.0,
        shortfall_cover_ratio=1.05,
        required_exit_price=101.0,
    )
    assert plan["allowed"] is False
    assert plan["reason"] == "capital_unlock_below_min_profit_floor"


def test_capital_unlock_sell_plan_blocks_without_inventory() -> None:
    plan = _capital_unlock_sell_plan(
        enabled=True,
        sell_profit_lock_require_cost_basis=True,
        bid_price=101.0,
        avg_entry_price=100.0,
        available_base_qty=0.0,
        min_unlock_notional_quote=10.0,
        shortfall_quote=20.0,
        shortfall_cover_ratio=1.05,
        required_exit_price=100.8,
    )
    assert plan["allowed"] is False
    assert plan["reason"] == "no_sellable_inventory"


def test_capital_unlock_sell_plan_blocks_missing_cost_basis_when_required() -> None:
    plan = _capital_unlock_sell_plan(
        enabled=True,
        sell_profit_lock_require_cost_basis=True,
        bid_price=101.0,
        avg_entry_price=0.0,
        available_base_qty=1.0,
        min_unlock_notional_quote=10.0,
        shortfall_quote=20.0,
        shortfall_cover_ratio=1.05,
        required_exit_price=0.0,
    )
    assert plan["allowed"] is False
    assert plan["reason"] == "missing_cost_basis"
