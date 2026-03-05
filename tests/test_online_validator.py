from __future__ import annotations

from autonomous_investment_robot.services.research.online_validator import (
    OnlineSignalValidator,
    OnlineValidatorConfig,
)


def test_online_validator_disables_underperforming_strategy_symbol() -> None:
    val = OnlineSignalValidator(
        OnlineValidatorConfig(
            enabled=True,
            window_trades=40,
            min_alpha_bps=-2.0,
            max_reject_rate=0.35,
            cooldown_s=600.0,
        )
    )
    ts = 1000.0
    for i in range(25):
        val.observe(
            symbol="XBTUSD",
            strategy="pairs_stat_arb",
            alpha_bps=-5.0,
            rejected=(i % 2 == 0),
            blocked_sell=False,
            now_ts=ts + i,
        )

    assert val.blocked(symbol="XBTUSD", strategy="pairs_stat_arb", now_ts=1100.0) is True


def test_online_validator_symbol_blocked_when_all_strategies_cooling_down() -> None:
    val = OnlineSignalValidator(
        OnlineValidatorConfig(
            enabled=True,
            window_trades=20,
            min_alpha_bps=-1.0,
            max_reject_rate=0.3,
            cooldown_s=500.0,
        )
    )
    for s in ("carry", "mean_reversion"):
        for i in range(15):
            val.observe(
                symbol="ETHEUR",
                strategy=s,
                alpha_bps=-4.0,
                rejected=True,
                blocked_sell=False,
                now_ts=2000.0 + i,
            )

    assert val.symbol_blocked(symbol="ETHEUR", strategies=["carry", "mean_reversion"], now_ts=2100.0) is True
