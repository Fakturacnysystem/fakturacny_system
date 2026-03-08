from __future__ import annotations

from dataclasses import dataclass
import math
import os
import time


def _is_rate_limit_reason(reason: str) -> bool:
    txt = str(reason or "").lower()
    return "rate limit" in txt or "429" in txt or "too many requests" in txt


@dataclass
class _TokenBucket:
    capacity: float
    refill_per_s: float
    tokens: float
    last_refill_ts: float

    @classmethod
    def from_per_min(cls, per_min: float, now_ts: float) -> _TokenBucket:
        cap = max(1.0, float(per_min))
        return cls(capacity=cap, refill_per_s=(cap / 60.0), tokens=cap, last_refill_ts=float(now_ts))

    def _refill(self, now_ts: float) -> None:
        now = float(now_ts)
        dt = max(0.0, now - float(self.last_refill_ts))
        if dt <= 0.0:
            return
        self.tokens = min(self.capacity, self.tokens + (dt * self.refill_per_s))
        self.last_refill_ts = now

    def try_consume(self, n: int, now_ts: float) -> bool:
        self._refill(now_ts)
        need = max(0.0, float(n))
        if self.tokens + 1e-12 < need:
            return False
        self.tokens -= need
        return True


@dataclass
class RateBudgetState:
    public_tokens: float
    private_tokens: float
    public_capacity: float
    private_capacity: float
    circuit_breaker_until_ts: float
    consecutive_rate_limit_errors: int


class RateBudget:
    def __init__(
        self,
        *,
        max_public_calls_per_min: int | None = None,
        max_private_calls_per_min: int | None = None,
        storm_threshold: int | None = None,
        breaker_cooldown_s: float | None = None,
    ) -> None:
        now = time.time()
        public_per_min = max(
            1,
            int(
                max_public_calls_per_min
                if max_public_calls_per_min is not None
                else int(float(os.getenv("AUTONOMOUS_MAX_PUBLIC_CALLS_PER_MIN", "120") or "120"))
            ),
        )
        private_per_min = max(
            1,
            int(
                max_private_calls_per_min
                if max_private_calls_per_min is not None
                else int(float(os.getenv("AUTONOMOUS_MAX_ORDERS_PER_MIN", "10") or "10"))
            ),
        )
        self.public_bucket = _TokenBucket.from_per_min(public_per_min, now)
        self.private_bucket = _TokenBucket.from_per_min(private_per_min, now)
        self.storm_threshold = max(
            2,
            int(
                storm_threshold
                if storm_threshold is not None
                else int(float(os.getenv("AUTONOMOUS_RATE_BUDGET_STORM_THRESHOLD", "5") or "5"))
            ),
        )
        self.breaker_cooldown_s = max(
            5.0,
            float(
                breaker_cooldown_s
                if breaker_cooldown_s is not None
                else float(os.getenv("AUTONOMOUS_RATE_BUDGET_BREAKER_COOLDOWN_S", "120") or "120")
            ),
        )
        self._consecutive_rate_limit_errors = 0
        self._circuit_breaker_until_ts = 0.0

    def allow_public(self, n: int = 1, *, now_ts: float | None = None) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        if self.circuit_breaker_active(now):
            return False
        return self.public_bucket.try_consume(max(1, int(n)), now)

    def allow_private(self, n: int = 1, *, now_ts: float | None = None) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        if self.circuit_breaker_active(now):
            return False
        return self.private_bucket.try_consume(max(1, int(n)), now)

    def record_reject(self, kind: str, reason: str, *, now_ts: float | None = None) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        k = str(kind or "").lower()
        if k not in {"public", "private"}:
            return
        if _is_rate_limit_reason(reason):
            self._consecutive_rate_limit_errors += 1
            if self._consecutive_rate_limit_errors >= self.storm_threshold:
                self._circuit_breaker_until_ts = max(
                    self._circuit_breaker_until_ts,
                    now + self.breaker_cooldown_s,
                )
        else:
            self._consecutive_rate_limit_errors = 0

    def circuit_breaker_active(self, now_ts: float | None = None) -> bool:
        now = time.time() if now_ts is None else float(now_ts)
        if now >= self._circuit_breaker_until_ts:
            return False
        return True

    def state(self, *, now_ts: float | None = None) -> RateBudgetState:
        now = time.time() if now_ts is None else float(now_ts)
        self.public_bucket._refill(now)
        self.private_bucket._refill(now)
        return RateBudgetState(
            public_tokens=float(self.public_bucket.tokens),
            private_tokens=float(self.private_bucket.tokens),
            public_capacity=float(self.public_bucket.capacity),
            private_capacity=float(self.private_bucket.capacity),
            circuit_breaker_until_ts=float(self._circuit_breaker_until_ts),
            consecutive_rate_limit_errors=int(self._consecutive_rate_limit_errors),
        )

