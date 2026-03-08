from __future__ import annotations

from autonomous_investment_robot.services.execution.rate_limit_governor import RateLimitGovernor


def test_rate_limit_storm_reduces_churn_but_keeps_60s_submit() -> None:
    gov = RateLimitGovernor(
        window_s=60.0,
        max_rate_limit_events_60s=3,
        storm_cooldown_s=120.0,
        retry_budget_per_endpoint=2,
    )
    now = 1000.0
    gov.record_error(endpoint="add_order", error_text="429 too many requests", now_ts=now)
    gov.record_error(endpoint="add_order", error_text="rate limit", now_ts=now + 1.0)
    gov.record_error(endpoint="cancel_order", error_text="rate limit", now_ts=now + 2.0)

    state = gov.state(now_ts=now + 2.0, base_extra_submissions=6)
    assert state.storm_active is True
    assert state.recommended_extra_submissions_max_per_min == 0
    assert gov.adjusted_reprice_interval(10.0, now_ts=now + 2.0) >= 20.0
    assert gov.adjusted_cancel_replace_budget(12, now_ts=now + 2.0) <= 6


def test_rate_limit_retry_budget() -> None:
    gov = RateLimitGovernor(retry_budget_per_endpoint=2)
    now = 100.0
    assert gov.allow_retry(endpoint="add_order", now_ts=now) is True
    gov.note_retry(endpoint="add_order", now_ts=now + 0.1)
    assert gov.allow_retry(endpoint="add_order", now_ts=now + 0.2) is True
    gov.note_retry(endpoint="add_order", now_ts=now + 0.3)
    assert gov.allow_retry(endpoint="add_order", now_ts=now + 0.4) is False


def test_rate_limit_governor_counts_temporary_lockout() -> None:
    gov = RateLimitGovernor(
        window_s=60.0,
        max_rate_limit_events_60s=1,
        storm_cooldown_s=30.0,
        retry_budget_per_endpoint=2,
    )
    now = 500.0
    gov.record_error(endpoint="balance", error_text="EGeneral:Temporary lockout", now_ts=now)
    state = gov.state(now_ts=now, base_extra_submissions=3)
    assert state.storm_active is True
    assert state.recent_events_60s >= 1
    assert state.recommended_extra_submissions_max_per_min == 0
