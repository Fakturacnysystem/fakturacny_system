from __future__ import annotations

import asyncio
import time
from collections import deque


class RateLimitGuard:
    """Simple sliding-window limiter for request pacing."""

    def __init__(self, max_events: int, window_seconds: float) -> None:
        self.max_events = max(1, int(max_events))
        self.window_seconds = max(0.1, float(window_seconds))
        self._events: deque[float] = deque()

    def _evict(self, now: float) -> None:
        while self._events and now - self._events[0] > self.window_seconds:
            self._events.popleft()

    def allow_now(self) -> bool:
        now = time.time()
        self._evict(now)
        return len(self._events) < self.max_events

    async def wait_for_slot(self) -> None:
        while True:
            now = time.time()
            self._evict(now)
            if len(self._events) < self.max_events:
                self._events.append(now)
                return
            sleep_s = max(0.01, self.window_seconds - (now - self._events[0]))
            await asyncio.sleep(sleep_s)

    def record(self) -> None:
        now = time.time()
        self._evict(now)
        self._events.append(now)
