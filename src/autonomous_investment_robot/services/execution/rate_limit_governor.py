from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import time


def _is_rate_limit_message(error_text: str) -> bool:
    txt = str(error_text or "").strip().lower()
    return (
        ("rate limit" in txt)
        or ("429" in txt)
        or ("too many requests" in txt)
        or ("temporary lockout" in txt)
    )


@dataclass
class RateLimitGovernorState:
    storm_active: bool
    recent_events_60s: int
    storm_until_ts: float
    recommended_extra_submissions_max_per_min: int
    recommended_reprice_interval_mult: float
    recommended_cancel_replace_budget_mult: float


class RateLimitGovernor:
    """Endpoint-aware rate-limit guard to prevent churn death spirals."""

    def __init__(
        self,
        *,
        window_s: float = 60.0,
        max_rate_limit_events_60s: int = 12,
        storm_cooldown_s: float = 120.0,
        retry_budget_per_endpoint: int = 2,
    ) -> None:
        self.window_s = max(10.0, float(window_s))
        self.max_rate_limit_events_60s = max(1, int(max_rate_limit_events_60s))
        self.storm_cooldown_s = max(10.0, float(storm_cooldown_s))
        self.retry_budget_per_endpoint = max(1, int(retry_budget_per_endpoint))
        self._endpoint_events: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=512))
        self._endpoint_retries: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=256))
        self._storm_until_ts = 0.0

    def _trim(self, dq: deque[float], now_ts: float) -> None:
        while dq and (now_ts - dq[0]) > self.window_s:
            dq.popleft()

    def record_error(self, *, endpoint: str, error_text: str, now_ts: float | None = None) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        if not _is_rate_limit_message(error_text):
            return
        key = str(endpoint or "unknown")
        events = self._endpoint_events[key]
        events.append(now)
        self._trim(events, now)
        if self.recent_events(now_ts=now) >= self.max_rate_limit_events_60s:
            self._storm_until_ts = max(self._storm_until_ts, now + self.storm_cooldown_s)

    def record_success(self, *, endpoint: str, now_ts: float | None = None) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        key = str(endpoint or "unknown")
        retries = self._endpoint_retries[key]
        self._trim(retries, now)
        if retries:
            retries.clear()

    def note_retry(self, *, endpoint: str, now_ts: float | None = None) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        key = str(endpoint or "unknown")
        dq = self._endpoint_retries[key]
        dq.append(now)
        self._trim(dq, now)

    def allow_retry(self, *, endpoint: str, now_ts: float | None = None) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        key = str(endpoint or "unknown")
        dq = self._endpoint_retries[key]
        self._trim(dq, now)
        return len(dq) < self.retry_budget_per_endpoint

    def recent_events(self, *, now_ts: float | None = None) -> int:
        now = time.time() if now_ts is None else float(now_ts)
        total = 0
        for dq in self._endpoint_events.values():
            self._trim(dq, now)
            total += len(dq)
        return int(total)

    def storm_active(self, *, now_ts: float | None = None) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        return now < float(self._storm_until_ts)

    def adjusted_extra_submissions(self, base_max_per_min: int, *, now_ts: float | None = None) -> int:
        if self.storm_active(now_ts=now_ts):
            return 0
        return max(0, int(base_max_per_min))

    def adjusted_reprice_interval(self, base_interval_s: float, *, now_ts: float | None = None) -> float:
        if self.storm_active(now_ts=now_ts):
            return max(float(base_interval_s), float(base_interval_s) * 2.0)
        return float(base_interval_s)

    def adjusted_cancel_replace_budget(self, base_budget: int, *, now_ts: float | None = None) -> int:
        if self.storm_active(now_ts=now_ts):
            return max(1, int(base_budget) // 2)
        return max(1, int(base_budget))

    def state(self, *, now_ts: float | None = None, base_extra_submissions: int = 0) -> RateLimitGovernorState:
        now = time.time() if now_ts is None else float(now_ts)
        storm = self.storm_active(now_ts=now)
        return RateLimitGovernorState(
            storm_active=storm,
            recent_events_60s=self.recent_events(now_ts=now),
            storm_until_ts=float(self._storm_until_ts),
            recommended_extra_submissions_max_per_min=self.adjusted_extra_submissions(
                int(base_extra_submissions),
                now_ts=now,
            ),
            recommended_reprice_interval_mult=2.0 if storm else 1.0,
            recommended_cancel_replace_budget_mult=0.5 if storm else 1.0,
        )
