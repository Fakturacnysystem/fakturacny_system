from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import time


@dataclass
class SubmissionStats:
    last_submission_ts: float
    submissions_per_minute: float
    fills_per_minute: float


class OrderSubmissionScheduler:
    """Enforces minimum order submission cadence in live loops."""

    def __init__(self, interval_s: float = 60.0, initial_last_submission_ts: float | None = None) -> None:
        self.interval_s = max(1.0, float(interval_s))
        if initial_last_submission_ts is None:
            self.last_submission_ts = time.time()
        else:
            self.last_submission_ts = max(0.0, float(initial_last_submission_ts))
        self._submission_ts: deque[float] = deque(maxlen=5000)
        self._fill_ts: deque[float] = deque(maxlen=5000)

    def should_submit(self, now_ts: float | None = None) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        return (now - self.last_submission_ts) >= self.interval_s

    def record_submission(self, *, now_ts: float | None = None, filled: bool = False) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        self.last_submission_ts = now
        self._submission_ts.append(now)
        if filled:
            self._fill_ts.append(now)

    def stats(self, now_ts: float | None = None) -> SubmissionStats:
        now = time.time() if now_ts is None else float(now_ts)
        while self._submission_ts and (now - self._submission_ts[0]) > 60.0:
            self._submission_ts.popleft()
        while self._fill_ts and (now - self._fill_ts[0]) > 60.0:
            self._fill_ts.popleft()
        return SubmissionStats(
            last_submission_ts=self.last_submission_ts,
            submissions_per_minute=float(len(self._submission_ts)),
            fills_per_minute=float(len(self._fill_ts)),
        )
