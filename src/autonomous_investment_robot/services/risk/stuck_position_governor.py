from __future__ import annotations

from dataclasses import dataclass
import math
import os
import time


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(float(str(raw).strip()))
    except Exception:
        return int(default)


@dataclass
class StuckPositionGovernorConfig:
    enabled: bool = True
    stuck_age_s: float = 3600.0
    stuck_dd_trigger: float = -0.012
    blocked_sells_trigger: int = 5
    blocked_sells_min_age_s: float = 900.0
    entries_pause_min_s: float = 900.0

    @classmethod
    def from_env(cls) -> "StuckPositionGovernorConfig":
        return cls(
            enabled=_env_bool("AUTONOMOUS_STUCK_GOVERNOR_ENABLED", True),
            stuck_age_s=max(60.0, _env_float("AUTONOMOUS_STUCK_AGE_S", 3600.0)),
            stuck_dd_trigger=min(-1e-6, _env_float("AUTONOMOUS_STUCK_DD_TRIGGER", -0.012)),
            blocked_sells_trigger=max(1, _env_int("AUTONOMOUS_STUCK_BLOCKED_SELLS_TRIGGER", 5)),
            blocked_sells_min_age_s=max(0.0, _env_float("AUTONOMOUS_STUCK_BLOCKED_SELLS_MIN_AGE_S", 900.0)),
            entries_pause_min_s=max(60.0, _env_float("AUTONOMOUS_STUCK_ENTRIES_PAUSE_MIN_S", 900.0)),
        )


@dataclass
class StuckPositionState:
    blocked_sell_count: int = 0
    entries_paused_until_ts: float = 0.0
    last_reason: str = ""
    stuck_events: int = 0


@dataclass
class StuckPositionDecision:
    symbol: str
    stuck: bool
    entries_paused: bool
    exits_only: bool
    reason: str
    blocked_sell_count: int
    entries_paused_until_ts: float
    recommended_entry_scale: float
    hedge_pressure: float


class StuckPositionGovernor:
    """Detects stuck positions and enforces symbol-local entries pause/exits-only modes."""

    def __init__(self, config: StuckPositionGovernorConfig | None = None) -> None:
        self.config = config or StuckPositionGovernorConfig.from_env()
        self._state: dict[str, StuckPositionState] = {}

    def _for(self, symbol: str) -> StuckPositionState:
        key = str(symbol or "").upper()
        if key not in self._state:
            self._state[key] = StuckPositionState()
        return self._state[key]

    def note_sell_profit_lock_block(self, symbol: str) -> None:
        st = self._for(symbol)
        st.blocked_sell_count += 1

    def note_sell_success(self, symbol: str) -> None:
        st = self._for(symbol)
        st.blocked_sell_count = max(0, st.blocked_sell_count - 1)

    def note_validation_underperformance(self, symbol: str) -> None:
        st = self._for(symbol)
        st.blocked_sell_count += 1
        st.last_reason = "validator_underperformance"

    def note_flat(self, symbol: str) -> None:
        st = self._for(symbol)
        st.blocked_sell_count = 0
        st.entries_paused_until_ts = 0.0
        st.last_reason = ""

    def observe(
        self,
        *,
        symbol: str,
        now_ts: float | None,
        has_position: bool,
        position_age_s: float,
        unrealized_pnl_ratio: float,
    ) -> StuckPositionDecision:
        now = time.time() if now_ts is None else float(now_ts)
        st = self._for(symbol)
        if not self.config.enabled:
            return StuckPositionDecision(
                symbol=str(symbol),
                stuck=False,
                entries_paused=False,
                exits_only=False,
                reason="stuck_governor_disabled",
                blocked_sell_count=st.blocked_sell_count,
                entries_paused_until_ts=st.entries_paused_until_ts,
                recommended_entry_scale=1.0,
                hedge_pressure=0.0,
            )

        reason = ""
        trigger = False
        pnl_ratio = float(unrealized_pnl_ratio)
        age_s = max(0.0, float(position_age_s))
        if has_position:
            if age_s >= self.config.stuck_age_s and pnl_ratio <= self.config.stuck_dd_trigger:
                trigger = True
                reason = "stuck_age_and_drawdown"
            elif age_s >= self.config.blocked_sells_min_age_s and st.blocked_sell_count >= self.config.blocked_sells_trigger:
                trigger = True
                reason = "stuck_blocked_sells"
        else:
            self.note_flat(symbol)
            st = self._for(symbol)

        if trigger:
            st.entries_paused_until_ts = max(
                st.entries_paused_until_ts,
                now + self.config.entries_pause_min_s,
            )
            st.stuck_events += 1
            st.last_reason = reason

        entries_paused = bool(now < st.entries_paused_until_ts)
        stuck = bool(trigger or entries_paused)
        pressure = 0.0
        if has_position and pnl_ratio < 0.0:
            pressure = min(1.0, abs(pnl_ratio) / max(abs(self.config.stuck_dd_trigger), 1e-9))
            if not math.isfinite(pressure):
                pressure = 0.0

        if stuck:
            recommended_entry_scale = 0.0 if entries_paused else 0.35
        else:
            recommended_entry_scale = 1.0

        return StuckPositionDecision(
            symbol=str(symbol),
            stuck=stuck,
            entries_paused=entries_paused,
            exits_only=stuck,
            reason=reason or st.last_reason or "ok",
            blocked_sell_count=st.blocked_sell_count,
            entries_paused_until_ts=st.entries_paused_until_ts,
            recommended_entry_scale=recommended_entry_scale,
            hedge_pressure=pressure,
        )

    def state_snapshot(self, now_ts: float | None = None) -> dict[str, dict[str, float | int | str | bool]]:
        now = time.time() if now_ts is None else float(now_ts)
        out: dict[str, dict[str, float | int | str | bool]] = {}
        for symbol, st in self._state.items():
            out[symbol] = {
                "blocked_sell_count": int(st.blocked_sell_count),
                "entries_paused_until_ts": float(st.entries_paused_until_ts),
                "entries_paused": bool(now < st.entries_paused_until_ts),
                "last_reason": str(st.last_reason),
                "stuck_events": int(st.stuck_events),
            }
        return out
