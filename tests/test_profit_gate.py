from __future__ import annotations

import math

from autonomous_investment_robot.services.execution.profit_gate import (
    PositionLot,
    ProfitGate,
    ProfitGateConfig,
)


def test_profit_gate_hard_floor_is_always_at_least_two_percent() -> None:
    gate = ProfitGate(ProfitGateConfig(min_net_profit_ratio=0.005))
    assert math.isclose(gate.config.min_net_profit_ratio, 0.02, rel_tol=0, abs_tol=1e-12)


def test_required_exit_price_long_includes_costs_and_target() -> None:
    gate = ProfitGate(
        ProfitGateConfig(
            min_net_profit_ratio=0.02,
            default_entry_fee_bps=10.0,
            default_exit_fee_bps=10.0,
            default_slippage_bps=5.0,
            accounting_method="fifo",
        )
    )
    req, matched = gate.required_exit_price_long(
        lots=[PositionLot(qty=1.0, entry_price=100.0)],
        exit_qty=1.0,
    )
    expected = (100.0 * (1.0 + 0.0015) * 1.02) / (1.0 - 0.0015)
    assert matched == 1.0
    assert math.isclose(req, expected, rel_tol=0, abs_tol=1e-9)


def test_required_exit_price_rounds_up_to_tick() -> None:
    gate = ProfitGate(ProfitGateConfig(min_net_profit_ratio=0.02, default_slippage_bps=0.0))
    req, _ = gate.required_exit_price_long(
        lots=[PositionLot(qty=1.0, entry_price=100.0)],
        exit_qty=1.0,
        tick_size=0.1,
        entry_fee_bps=0.0,
        exit_fee_bps=0.0,
        slippage_bps=0.0,
    )
    # 100 * 1.02 = 102.0 already aligned
    assert math.isclose(req, 102.0, rel_tol=0, abs_tol=1e-12)

    req2, _ = gate.required_exit_price_long(
        lots=[PositionLot(qty=1.0, entry_price=100.03)],
        exit_qty=1.0,
        tick_size=0.1,
        entry_fee_bps=0.0,
        exit_fee_bps=0.0,
        slippage_bps=0.0,
    )
    assert math.isclose(req2, 102.1, rel_tol=0, abs_tol=1e-12)


def test_fifo_partial_eligibility_when_only_first_lot_is_profitable() -> None:
    gate = ProfitGate(ProfitGateConfig(min_net_profit_ratio=0.02, accounting_method="fifo", default_slippage_bps=0.0))
    lots = [
        PositionLot(qty=1.0, entry_price=100.0),
        PositionLot(qty=1.0, entry_price=110.0),
    ]
    decision = gate.can_close_long(
        lots=lots,
        exit_price=103.0,
        exit_qty=2.0,
        entry_fee_bps=0.0,
        exit_fee_bps=0.0,
        slippage_bps=0.0,
    )
    assert decision.allowed is False
    assert decision.eligible_qty == 1.0
    assert decision.reason == "profit_gate_block"


def test_required_exit_price_short_respects_two_percent_net() -> None:
    gate = ProfitGate(ProfitGateConfig(min_net_profit_ratio=0.02, default_slippage_bps=0.0))
    max_exit, matched = gate.required_exit_price_short(
        lots=[PositionLot(qty=2.0, entry_price=100.0)],
        close_qty=1.0,
        tick_size=0.1,
        entry_fee_bps=0.0,
        exit_fee_bps=0.0,
        slippage_bps=0.0,
    )
    assert matched == 1.0
    assert math.isclose(max_exit, 98.0, rel_tol=0, abs_tol=1e-12)


def test_required_exit_price_short_includes_costs_and_rounds_down() -> None:
    gate = ProfitGate(
        ProfitGateConfig(
            min_net_profit_ratio=0.02,
            default_entry_fee_bps=12.0,
            default_exit_fee_bps=18.0,
            default_slippage_bps=3.0,
        )
    )
    max_exit, _ = gate.required_exit_price_short(
        lots=[PositionLot(qty=1.0, entry_price=100.0)],
        close_qty=1.0,
        tick_size=0.01,
    )
    # Must be below 98 due to fees/slippage.
    assert max_exit < 98.0


def test_can_close_short_blocks_when_buyback_price_too_high() -> None:
    gate = ProfitGate(ProfitGateConfig(min_net_profit_ratio=0.02, default_slippage_bps=0.0))
    decision = gate.can_close_short(
        lots=[PositionLot(qty=1.0, entry_price=100.0)],
        exit_price=99.5,
        close_qty=1.0,
        entry_fee_bps=0.0,
        exit_fee_bps=0.0,
        slippage_bps=0.0,
    )
    assert decision.allowed is False
    assert decision.reason == "profit_gate_block"
    assert decision.required_exit_price == 98.0
    assert decision.eligible_qty == 0.0


def test_can_close_short_allows_when_buyback_price_meets_gate() -> None:
    gate = ProfitGate(ProfitGateConfig(min_net_profit_ratio=0.02, default_slippage_bps=0.0))
    decision = gate.can_close_short(
        lots=[PositionLot(qty=2.0, entry_price=100.0)],
        exit_price=98.0,
        close_qty=1.0,
        entry_fee_bps=0.0,
        exit_fee_bps=0.0,
        slippage_bps=0.0,
    )
    assert decision.allowed is True
    assert decision.reason == "ok"
    assert decision.matched_qty == 1.0
    assert decision.eligible_qty == 1.0


def test_fifo_short_partial_eligibility_with_multiple_lots() -> None:
    gate = ProfitGate(ProfitGateConfig(min_net_profit_ratio=0.02, accounting_method="fifo", default_slippage_bps=0.0))
    lots = [
        PositionLot(qty=1.0, entry_price=100.0),  # requires <= 98
        PositionLot(qty=1.0, entry_price=110.0),  # requires <= 107.8
    ]
    decision = gate.can_close_short(
        lots=lots,
        exit_price=99.0,
        close_qty=2.0,
        entry_fee_bps=0.0,
        exit_fee_bps=0.0,
        slippage_bps=0.0,
    )
    assert decision.allowed is False
    assert decision.eligible_qty == 0.0

def test_average_accounting_requires_blended_exit() -> None:
    gate = ProfitGate(ProfitGateConfig(min_net_profit_ratio=0.02, accounting_method="average", default_slippage_bps=0.0))
    lots = [
        PositionLot(qty=1.0, entry_price=100.0),
        PositionLot(qty=1.0, entry_price=110.0),
    ]
    req, matched = gate.required_exit_price_long(
        lots=lots,
        exit_qty=2.0,
        entry_fee_bps=0.0,
        exit_fee_bps=0.0,
        slippage_bps=0.0,
    )
    # Average entry = 105, +2% => 107.1
    assert matched == 2.0
    assert math.isclose(req, 107.1, rel_tol=0, abs_tol=1e-12)
