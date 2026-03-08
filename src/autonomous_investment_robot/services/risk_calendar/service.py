from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class BlackoutWindow:
    day: str
    start_minute: int
    end_minute: int


class RiskCalendarService:
    """
    Deterministic blackout window checker.
    Format:
      "mon:09:00-10:00,tue:14:30-15:00"
    """

    _day_map = {
        "mon": 0,
        "tue": 1,
        "wed": 2,
        "thu": 3,
        "fri": 4,
        "sat": 5,
        "sun": 6,
    }

    def __init__(self, windows_raw: str = "") -> None:
        self.windows = self.parse_windows(windows_raw)

    @classmethod
    def parse_windows(cls, raw: str) -> list[BlackoutWindow]:
        out: list[BlackoutWindow] = []
        text = str(raw or "").strip()
        if not text:
            return out
        for item in text.split(","):
            token = item.strip().lower()
            if not token or ":" not in token or "-" not in token:
                continue
            try:
                day, rest = token.split(":", 1)
                start, end = rest.split("-", 1)
                if day not in cls._day_map:
                    continue
                sh, sm = [int(x) for x in start.split(":")]
                eh, em = [int(x) for x in end.split(":")]
                start_m = sh * 60 + sm
                end_m = eh * 60 + em
            except Exception:
                continue
            if start_m < 0 or start_m > 1439 or end_m < 0 or end_m > 1439:
                continue
            out.append(BlackoutWindow(day=day, start_minute=start_m, end_minute=end_m))
        return out

    def in_blackout(self, now_ts: float) -> bool:
        if not self.windows:
            return False
        dt = datetime.fromtimestamp(float(now_ts), tz=timezone.utc)
        weekday = int(dt.weekday())
        minute = int(dt.hour * 60 + dt.minute)
        for w in self.windows:
            if self._day_map.get(w.day) != weekday:
                continue
            if w.start_minute <= minute <= w.end_minute:
                return True
        return False

