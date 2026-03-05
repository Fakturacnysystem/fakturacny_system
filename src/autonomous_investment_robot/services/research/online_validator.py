from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import os
import time


@dataclass
class OnlineValidatorConfig:
    enabled: bool = True
    window_trades: int = 200
    min_alpha_bps: float = -10.0
    max_reject_rate: float = 0.35
    cooldown_s: float = 3600.0

    @classmethod
    def from_env(cls) -> "OnlineValidatorConfig":
        def _b(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return bool(default)
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}

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
            enabled=_b("AUTONOMOUS_ONLINE_VALIDATION_ENABLED", True),
            window_trades=max(20, _i("AUTONOMOUS_VALIDATION_WINDOW_TRADES", 200)),
            min_alpha_bps=_f("AUTONOMOUS_VALIDATION_MIN_ALPHA_BPS", -10.0),
            max_reject_rate=max(0.01, min(1.0, _f("AUTONOMOUS_VALIDATION_MAX_REJECT_RATE", 0.35))),
            cooldown_s=max(60.0, _f("AUTONOMOUS_VALIDATION_COOLDOWN_S", 3600.0)),
        )


@dataclass
class OnlineValidationEvent:
    ts: float
    alpha_bps: float
    expected_alpha_bps: float
    rejected: bool
    blocked_sell: bool


@dataclass
class OnlineValidationStats:
    trades: int
    mean_alpha_bps: float
    reject_rate: float
    blocked_sell_rate: float
    cooldown_until_ts: float


class OnlineSignalValidator:
    """Lightweight online validator for strategy/symbol effectiveness."""

    def __init__(self, config: OnlineValidatorConfig | None = None) -> None:
        self.config = config or OnlineValidatorConfig.from_env()
        self._events: dict[tuple[str, str], deque[OnlineValidationEvent]] = defaultdict(
            lambda: deque(maxlen=self.config.window_trades)
        )
        self._cooldown_until: dict[tuple[str, str], float] = {}

    def _key(self, symbol: str, strategy: str) -> tuple[str, str]:
        return (str(symbol or "").upper(), str(strategy or "").strip().lower() or "unknown")

    def observe(
        self,
        *,
        symbol: str,
        strategy: str,
        alpha_bps: float,
        expected_alpha_bps: float | None = None,
        rejected: bool,
        blocked_sell: bool,
        now_ts: float | None = None,
    ) -> None:
        if not self.config.enabled:
            return
        now = time.time() if now_ts is None else float(now_ts)
        key = self._key(symbol, strategy)
        self._events[key].append(
            OnlineValidationEvent(
                ts=now,
                alpha_bps=float(alpha_bps),
                expected_alpha_bps=float(alpha_bps if expected_alpha_bps is None else expected_alpha_bps),
                rejected=bool(rejected),
                blocked_sell=bool(blocked_sell),
            )
        )
        self._maybe_disable(key, now)

    def _maybe_disable(self, key: tuple[str, str], now: float) -> None:
        events = self._events.get(key)
        if not events:
            return
        if len(events) < max(10, self.config.window_trades // 4):
            return
        trades = len(events)
        mean_alpha = sum(e.alpha_bps for e in events) / max(1, trades)
        mean_alpha_delta = sum((e.alpha_bps - e.expected_alpha_bps) for e in events) / max(1, trades)
        reject_rate = sum(1 for e in events if e.rejected) / max(1, trades)
        if mean_alpha <= self.config.min_alpha_bps or mean_alpha_delta <= self.config.min_alpha_bps or reject_rate >= self.config.max_reject_rate:
            self._cooldown_until[key] = max(self._cooldown_until.get(key, 0.0), now + self.config.cooldown_s)

    def blocked(self, *, symbol: str, strategy: str, now_ts: float | None = None) -> bool:
        if not self.config.enabled:
            return False
        now = time.time() if now_ts is None else float(now_ts)
        return now < float(self._cooldown_until.get(self._key(symbol, strategy), 0.0) or 0.0)

    def symbol_blocked(self, *, symbol: str, strategies: list[str], now_ts: float | None = None) -> bool:
        if not self.config.enabled:
            return False
        if not strategies:
            return False
        now = time.time() if now_ts is None else float(now_ts)
        return all(self.blocked(symbol=symbol, strategy=s, now_ts=now) for s in strategies)

    def stats(self, *, symbol: str, strategy: str) -> OnlineValidationStats:
        key = self._key(symbol, strategy)
        events = list(self._events.get(key, []))
        trades = len(events)
        mean_alpha = 0.0 if trades <= 0 else sum(e.alpha_bps for e in events) / trades
        reject_rate = 0.0 if trades <= 0 else sum(1 for e in events if e.rejected) / trades
        blocked_sell_rate = 0.0 if trades <= 0 else sum(1 for e in events if e.blocked_sell) / trades
        return OnlineValidationStats(
            trades=trades,
            mean_alpha_bps=mean_alpha,
            reject_rate=reject_rate,
            blocked_sell_rate=blocked_sell_rate,
            cooldown_until_ts=float(self._cooldown_until.get(key, 0.0) or 0.0),
        )

    def snapshot(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        now = time.time()
        for (symbol, strategy), events in self._events.items():
            stats = self.stats(symbol=symbol, strategy=strategy)
            out[f"{symbol}:{strategy}"] = {
                "trades": float(stats.trades),
                "mean_alpha_bps": float(stats.mean_alpha_bps),
                "reject_rate": float(stats.reject_rate),
                "blocked_sell_rate": float(stats.blocked_sell_rate),
                "blocked": 1.0 if now < stats.cooldown_until_ts else 0.0,
                "cooldown_until_ts": float(stats.cooldown_until_ts),
            }
        return out
