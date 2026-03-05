from __future__ import annotations

import time

from autonomous_investment_robot.core.order_scheduler import OrderSubmissionScheduler


def test_scheduler_requires_submission_after_interval() -> None:
    sch = OrderSubmissionScheduler(interval_s=1.0)
    now = time.time()
    assert sch.should_submit(now_ts=now) is False
    assert sch.should_submit(now_ts=now + 1.05) is True


def test_scheduler_records_submissions_and_fills() -> None:
    sch = OrderSubmissionScheduler(interval_s=1.0)
    now = time.time()
    sch.record_submission(now_ts=now, filled=False)
    sch.record_submission(now_ts=now + 0.1, filled=True)
    stats = sch.stats(now_ts=now + 0.2)
    assert stats.submissions_per_minute == 2.0
    assert stats.fills_per_minute == 1.0
