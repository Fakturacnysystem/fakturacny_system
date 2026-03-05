from __future__ import annotations

from autonomous_investment_robot.services.risk.hedge_manager import HedgeConfig, HedgeManager


def test_hedge_manager_opens_tranche_for_stuck_position() -> None:
    mgr = HedgeManager(
        HedgeConfig(
            enabled=True,
            max_ratio=0.8,
            step_ratio=0.2,
            dd_step=0.008,
            min_notional=10.0,
            max_notional_per_symbol=200.0,
            close_profit_net=0.02,
            funding_window_s=1200.0,
        )
    )
    dec = mgr.maybe_open_hedge(
        symbol="XBTUSD",
        perps_symbol="PI_XBTUSD",
        spot_signed_exposure_quote=100.0,
        unrealized_pnl_ratio=-0.02,
        pressure=1.0,
        funding_rate=0.0,
        funding_eta_s=None,
        now_ts=100.0,
        perps_available=True,
    )
    assert dec.should_open is True
    assert dec.action is not None
    assert dec.action.symbol == "PI_XBTUSD"
    assert dec.action.side == "sell"
    assert dec.action.target_notional_quote >= 10.0


def test_hedge_close_requires_profit_gate_2pct() -> None:
    mgr = HedgeManager(HedgeConfig(enabled=True, close_profit_net=0.02))
    assert mgr.can_close_hedge(profit_gate_allowed=True, expected_net_profit_ratio=0.019) is False
    assert mgr.can_close_hedge(profit_gate_allowed=False, expected_net_profit_ratio=0.03) is False
    assert mgr.can_close_hedge(profit_gate_allowed=True, expected_net_profit_ratio=0.02) is True
