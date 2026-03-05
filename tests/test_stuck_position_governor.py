from __future__ import annotations

from autonomous_investment_robot.services.risk.stuck_position_governor import (
    StuckPositionGovernor,
    StuckPositionGovernorConfig,
)


def test_stuck_governor_triggers_entries_pause_on_age_and_dd() -> None:
    gov = StuckPositionGovernor(
        StuckPositionGovernorConfig(
            enabled=True,
            stuck_age_s=3600.0,
            stuck_dd_trigger=-0.01,
            blocked_sells_trigger=5,
            entries_pause_min_s=900.0,
        )
    )
    out = gov.observe(
        symbol="XBTUSD",
        now_ts=1000.0,
        has_position=True,
        position_age_s=7200.0,
        unrealized_pnl_ratio=-0.02,
    )
    assert out.stuck is True
    assert out.entries_paused is True
    assert out.exits_only is True
    assert out.reason == "stuck_age_and_drawdown"


def test_stuck_governor_triggers_on_blocked_sell_streak() -> None:
    gov = StuckPositionGovernor(
        StuckPositionGovernorConfig(
            enabled=True,
            stuck_age_s=3600.0,
            stuck_dd_trigger=-0.02,
            blocked_sells_trigger=3,
            entries_pause_min_s=300.0,
        )
    )
    gov.note_sell_profit_lock_block("XBTUSD")
    gov.note_sell_profit_lock_block("XBTUSD")
    gov.note_sell_profit_lock_block("XBTUSD")
    out = gov.observe(
        symbol="XBTUSD",
        now_ts=2000.0,
        has_position=True,
        position_age_s=120.0,
        unrealized_pnl_ratio=-0.001,
    )
    assert out.stuck is True
    assert out.reason == "stuck_blocked_sells"
    assert out.blocked_sell_count >= 3
