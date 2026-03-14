from __future__ import annotations

from autonomous_investment_robot.core.orchestrator import _compute_risk_notional_caps


def test_risk_caps_convert_risk_budgets_to_notional_caps() -> None:
    caps = _compute_risk_notional_caps(
        equity_quote=1000.0,
        current_exposure_quote=100.0,
        risk_per_trade_ratio=0.0025,
        max_portfolio_heat_ratio=0.0125,
        max_symbol_exposure_ratio=0.0075,
        risk_stop_pct=0.005,
    )
    assert caps["risk_budget_quote"] == 2.5
    assert caps["portfolio_heat_budget_quote"] == 12.5
    assert caps["symbol_heat_budget_quote"] == 7.5
    assert caps["risk_trade_notional_cap"] == 500.0
    assert caps["portfolio_heat_notional_cap"] == 2500.0
    assert caps["symbol_heat_notional_cap"] == 1500.0
    assert caps["portfolio_heat_remaining_notional_cap"] == 2400.0
    assert caps["symbol_heat_remaining_notional_cap"] == 1400.0


def test_risk_caps_clamp_invalid_inputs() -> None:
    caps = _compute_risk_notional_caps(
        equity_quote=-5.0,
        current_exposure_quote=-1.0,
        risk_per_trade_ratio=-3.0,
        max_portfolio_heat_ratio=9.0,
        max_symbol_exposure_ratio=9.0,
        risk_stop_pct=0.0,
    )
    assert caps["equity_quote"] == 0.0
    assert caps["current_exposure_quote"] == 0.0
    assert caps["risk_budget_quote"] == 0.0
    assert caps["risk_trade_notional_cap"] == 0.0
    assert caps["portfolio_heat_remaining_notional_cap"] == 0.0
    assert caps["symbol_heat_remaining_notional_cap"] == 0.0
