from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import os
import time


@dataclass
class OrderChurnConfig:
    max_cancel_replace_per_min: int = 60
    budget_per_symbol_per_min: int = 12
    min_move_ticks: int = 1
    min_time_between_reprice_s: float = 3.0
    rate_limit_storm_cooldown_s: float = 60.0

    @classmethod
    def from_env(cls) -> "OrderChurnConfig":
        def _f(name: str, default: float) -> float:
            raw = os.getenv(name)
            if raw is None:
                return float(default)
            try:
                return float(str(raw).strip())
            except Exception:
                return float(default)

        def _i(name: str, default: int) -> int:
            raw = os.getenv(name)
            if raw is None:
                return int(default)
            try:
                return int(float(str(raw).strip()))
            except Exception:
                return int(default)

        return cls(
            max_cancel_replace_per_min=max(1, _i("AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN", 60)),
            budget_per_symbol_per_min=max(
                1,
                _i("AUTONOMOUS_CANCEL_REPLACE_BUDGET_PER_SYMBOL_PER_MIN", 12),
            ),
            min_move_ticks=max(1, _i("AUTONOMOUS_EXIT_CANCEL_REPLACE_MIN_MOVE_TICKS", 1)),
            min_time_between_reprice_s=max(
                1.0,
                _f("AUTONOMOUS_EXIT_MIN_TIME_BETWEEN_REPRICE_S", 3.0),
            ),
            rate_limit_storm_cooldown_s=max(
                10.0,
                _f("AUTONOMOUS_RATE_LIMIT_STORM_COOLDOWN_S", 60.0),
            ),
        )


@dataclass
class ChurnDecision:
    allowed: bool
    reason: str


@dataclass
class ChurnRecommendations:
    max_cancel_replace_per_min: int
    budget_per_symbol_per_min: int
    reprice_interval_multiplier: float
    extra_submissions_allowed: bool


class OrderChurnController:
    """Anti-churn guard with storm-aware throttling."""

    def __init__(self, config: OrderChurnConfig | None = None) -> None:
        self.config = config or OrderChurnConfig.from_env()
        self._global_cancel_replace: deque[float] = deque(maxlen=8192)
        self._per_symbol_cancel_replace: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=2048))
        self._last_reprice_ts: dict[str, float] = {}
        self._storm_until_ts: float = 0.0

    def _trim(self, dq: deque[float], now_ts: float) -> None:
        while dq and (now_ts - dq[0]) > 60.0:
            dq.popleft()

    def note_rate_limit_storm(self, now_ts: float | None = None) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        self._storm_until_ts = max(self._storm_until_ts, now + self.config.rate_limit_storm_cooldown_s)

    def storm_active(self, now_ts: float | None = None) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        return now < self._storm_until_ts

    def _effective_limits(self, now_ts: float) -> tuple[int, int]:
        g = int(self.config.max_cancel_replace_per_min)
        s = int(self.config.budget_per_symbol_per_min)
        if self.storm_active(now_ts=now_ts):
            g = max(1, g // 2)
            s = max(1, s // 2)
        return g, s

    def allow_reprice(self, *, symbol: str, now_ts: float | None, move_ticks: int) -> ChurnDecision:
        now = time.time() if now_ts is None else float(now_ts)
        sym = str(symbol or "").upper()
        if int(move_ticks) < int(self.config.min_move_ticks):
            return ChurnDecision(False, "move_below_min_ticks")

        last = float(self._last_reprice_ts.get(sym, 0.0) or 0.0)
        if (now - last) < self.config.min_time_between_reprice_s:
            return ChurnDecision(False, "reprice_min_time")

        self._trim(self._global_cancel_replace, now)
        per = self._per_symbol_cancel_replace[sym]
        self._trim(per, now)
        g_lim, s_lim = self._effective_limits(now)

        if len(self._global_cancel_replace) >= g_lim:
            return ChurnDecision(False, "global_cancel_replace_budget")
        if len(per) >= s_lim:
            return ChurnDecision(False, "symbol_cancel_replace_budget")

        return ChurnDecision(True, "ok")

    def note_cancel_replace(self, *, symbol: str, now_ts: float | None = None) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        sym = str(symbol or "").upper()
        self._global_cancel_replace.append(now)
        self._per_symbol_cancel_replace[sym].append(now)
        self._last_reprice_ts[sym] = now

    def recommendations(self, *, now_ts: float | None = None) -> ChurnRecommendations:
        now = time.time() if now_ts is None else float(now_ts)
        g_lim, s_lim = self._effective_limits(now)
        storm = self.storm_active(now_ts=now)
        return ChurnRecommendations(
            max_cancel_replace_per_min=g_lim,
            budget_per_symbol_per_min=s_lim,
            reprice_interval_multiplier=2.0 if storm else 1.0,
            extra_submissions_allowed=not storm,
        )
