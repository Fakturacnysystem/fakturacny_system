from __future__ import annotations

from autonomous_investment_robot.services.execution.order_churn_controller import (
    OrderChurnConfig,
    OrderChurnController,
)


def test_order_churn_blocks_reprice_when_too_soon_or_budget_hit() -> None:
    ctrl = OrderChurnController(
        OrderChurnConfig(
            max_cancel_replace_per_min=2,
            budget_per_symbol_per_min=1,
            min_move_ticks=1,
            min_time_between_reprice_s=5.0,
            rate_limit_storm_cooldown_s=60.0,
        )
    )
    d1 = ctrl.allow_reprice(symbol="XBTUSD", now_ts=100.0, move_ticks=1)
    assert d1.allowed is True
    ctrl.note_cancel_replace(symbol="XBTUSD", now_ts=100.0)

    d2 = ctrl.allow_reprice(symbol="XBTUSD", now_ts=101.0, move_ticks=2)
    assert d2.allowed is False
    assert d2.reason == "reprice_min_time"

    d3 = ctrl.allow_reprice(symbol="XBTUSD", now_ts=106.0, move_ticks=2)
    assert d3.allowed is False
    assert d3.reason == "symbol_cancel_replace_budget"


def test_order_churn_storm_reduces_recommendations() -> None:
    ctrl = OrderChurnController(
        OrderChurnConfig(
            max_cancel_replace_per_min=60,
            budget_per_symbol_per_min=12,
            min_move_ticks=1,
            min_time_between_reprice_s=3.0,
            rate_limit_storm_cooldown_s=60.0,
        )
    )
    normal = ctrl.recommendations(now_ts=200.0)
    assert normal.max_cancel_replace_per_min == 60
    assert normal.budget_per_symbol_per_min == 12
    assert normal.extra_submissions_allowed is True

    ctrl.note_rate_limit_storm(now_ts=200.0)
    storm = ctrl.recommendations(now_ts=201.0)
    assert storm.max_cancel_replace_per_min < normal.max_cancel_replace_per_min
    assert storm.budget_per_symbol_per_min < normal.budget_per_symbol_per_min
    assert storm.extra_submissions_allowed is False
