from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass
class SpreadSpikeState:
    active: bool
    spread_bps: float
    median_spread_bps: float
    hold_until_ts: float


class SpreadSpikeDetector:
    def __init__(
        self,
        *,
        mult: float = 2.5,
        min_bps: float = 8.0,
        hold_s: float = 45.0,
        window: int = 120,
    ) -> None:
        self.mult = max(1.0, float(mult))
        self.min_bps = max(0.0, float(min_bps))
        self.hold_s = max(1.0, float(hold_s))
        self._spreads = deque(maxlen=max(10, int(window)))
        self._hold_until_ts = 0.0

    def _median(self) -> float:
        if not self._spreads:
            return 0.0
        arr = sorted(float(x) for x in self._spreads)
        n = len(arr)
        if n % 2:
            return arr[n // 2]
        return (arr[(n // 2) - 1] + arr[n // 2]) / 2.0

    def update(self, *, spread_bps: float, now_ts: float) -> SpreadSpikeState:
        s = max(0.0, float(spread_bps))
        self._spreads.append(s)
        med = self._median()
        threshold = max(self.min_bps, med * self.mult)
        if s >= threshold:
            self._hold_until_ts = max(self._hold_until_ts, float(now_ts) + self.hold_s)
        active = float(now_ts) < self._hold_until_ts
        return SpreadSpikeState(
            active=bool(active),
            spread_bps=s,
            median_spread_bps=float(med),
            hold_until_ts=float(self._hold_until_ts),
        )

