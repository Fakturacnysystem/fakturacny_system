from __future__ import annotations

from autonomous_investment_robot.services.reliability.rate_budget import RateBudget


def test_rate_budget_depletion_blocks_calls():
    rb = RateBudget(
        max_public_calls_per_min=2,
        max_private_calls_per_min=1,
        storm_threshold=3,
        breaker_cooldown_s=30.0,
    )
    now = 1000.0
    assert rb.allow_public(now_ts=now) is True
    assert rb.allow_public(now_ts=now) is True
    assert rb.allow_public(now_ts=now) is False
    assert rb.allow_private(now_ts=now) is True
    assert rb.allow_private(now_ts=now) is False


def test_rate_limit_storm_triggers_circuit_breaker():
    rb = RateBudget(
        max_public_calls_per_min=10,
        max_private_calls_per_min=10,
        storm_threshold=2,
        breaker_cooldown_s=20.0,
    )
    now = 2000.0
    rb.record_reject("private", "Kraken rate limit: 429", now_ts=now)
    assert rb.circuit_breaker_active(now_ts=now) is False
    rb.record_reject("private", "Kraken rate limit exceeded", now_ts=now + 1.0)
    assert rb.circuit_breaker_active(now_ts=now + 1.0) is True
    assert rb.allow_private(now_ts=now + 2.0) is False
    assert rb.circuit_breaker_active(now_ts=now + 30.0) is False

