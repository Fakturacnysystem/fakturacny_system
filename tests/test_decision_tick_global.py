from __future__ import annotations

from autonomous_investment_robot.services.ops import DecisionTickEmitter


def test_decision_tick_global_emits_once_per_bucket():
    em = DecisionTickEmitter(interval_s=60.0, per_symbol=False)
    assert em.should_emit(symbol="XBTUSD", now_ts=120.0) is True
    assert em.should_emit(symbol="ETHEUR", now_ts=121.0) is False
    assert em.should_emit(symbol="XBTUSD", now_ts=181.0) is True


def test_decision_tick_per_symbol_mode_emits_per_symbol():
    em = DecisionTickEmitter(interval_s=60.0, per_symbol=True)
    assert em.should_emit(symbol="XBTUSD", now_ts=300.0) is True
    assert em.should_emit(symbol="ETHEUR", now_ts=301.0) is True
    assert em.should_emit(symbol="XBTUSD", now_ts=302.0) is False

