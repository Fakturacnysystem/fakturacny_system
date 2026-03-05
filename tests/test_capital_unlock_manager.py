from __future__ import annotations

from autonomous_investment_robot.services.risk.capital_unlock_manager import (
    CapitalUnlockConfig,
    CapitalUnlockManager,
)


def test_capital_unlock_reassigns_budget_on_locked_exposure_ratio() -> None:
    mgr = CapitalUnlockManager(
        CapitalUnlockConfig(
            enabled=True,
            locked_exposure_ratio_trigger=0.35,
            median_hold_s_trigger=7200.0,
            stuck_entry_scale=0.2,
            redirect_topk=30,
        )
    )
    dec = mgr.evaluate(
        now_ts=1000.0,
        base_topk=60,
        exposure_by_symbol_quote={"XBTUSD": 450.0, "ETHEUR": 150.0},
        position_age_by_symbol_s={"XBTUSD": 4000.0, "ETHEUR": 200.0},
        stuck_symbols={"XBTUSD"},
        total_capital_quote=1000.0,
    )
    assert dec.redirect_mode is True
    assert dec.reason == "locked_exposure_ratio"
    assert dec.locked_exposure_ratio >= 0.35
    assert dec.recommended_topk == 30
    assert dec.symbol_entry_scale.get("XBTUSD") == 0.2


def test_capital_unlock_triggers_on_median_hold_time() -> None:
    mgr = CapitalUnlockManager(
        CapitalUnlockConfig(
            enabled=True,
            locked_exposure_ratio_trigger=0.9,
            median_hold_s_trigger=7200.0,
            stuck_entry_scale=0.25,
            redirect_topk=25,
        )
    )
    dec = mgr.evaluate(
        now_ts=2000.0,
        base_topk=60,
        exposure_by_symbol_quote={"XBTUSD": 100.0, "ETHEUR": 100.0},
        position_age_by_symbol_s={"XBTUSD": 9000.0, "ETHEUR": 9500.0},
        stuck_symbols={"XBTUSD", "ETHEUR"},
        total_capital_quote=2000.0,
    )
    assert dec.redirect_mode is True
    assert dec.reason == "median_hold_time"
    assert dec.median_stuck_hold_s >= 7200.0
    assert dec.recommended_topk == 25


def test_capital_unlock_releases_after_unstuck() -> None:
    mgr = CapitalUnlockManager(
        CapitalUnlockConfig(
            enabled=True,
            locked_exposure_ratio_trigger=0.35,
            median_hold_s_trigger=7200.0,
            stuck_entry_scale=0.2,
            redirect_topk=30,
        )
    )
    dec_locked = mgr.evaluate(
        now_ts=1000.0,
        base_topk=60,
        exposure_by_symbol_quote={"XBTUSD": 500.0},
        position_age_by_symbol_s={"XBTUSD": 9000.0},
        stuck_symbols={"XBTUSD"},
        total_capital_quote=1000.0,
    )
    assert dec_locked.redirect_mode is True
    dec_released = mgr.evaluate(
        now_ts=2000.0,
        base_topk=60,
        exposure_by_symbol_quote={"XBTUSD": 50.0},
        position_age_by_symbol_s={"XBTUSD": 60.0},
        stuck_symbols=set(),
        total_capital_quote=1000.0,
    )
    assert dec_released.redirect_mode is False
    assert dec_released.recommended_topk == 60
