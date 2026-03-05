from __future__ import annotations

from dataclasses import dataclass
import os
import statistics
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
class CapitalUnlockConfig:
    enabled: bool = True
    locked_exposure_ratio_trigger: float = 0.35
    median_hold_s_trigger: float = 7200.0
    stuck_entry_scale: float = 0.20
    redirect_topk: int = 30

    @classmethod
    def from_env(cls) -> "CapitalUnlockConfig":
        return cls(
            enabled=_env_bool("AUTONOMOUS_CAPITAL_UNLOCK_ENABLED", True),
            locked_exposure_ratio_trigger=max(
                0.05,
                min(0.95, _env_float("AUTONOMOUS_CAPITAL_LOCKED_RATIO_TRIGGER", 0.35)),
            ),
            median_hold_s_trigger=max(
                300.0,
                _env_float("AUTONOMOUS_CAPITAL_MEDIAN_HOLD_S_TRIGGER", 7200.0),
            ),
            stuck_entry_scale=max(
                0.0,
                min(1.0, _env_float("AUTONOMOUS_CAPITAL_STUCK_ENTRY_SCALE", 0.20)),
            ),
            redirect_topk=max(1, _env_int("AUTONOMOUS_CAPITAL_REDIRECT_TOPK", 30)),
        )


@dataclass
class CapitalUnlockDecision:
    redirect_mode: bool
    reason: str
    locked_exposure_ratio: float
    median_stuck_hold_s: float
    recommended_topk: int
    symbol_entry_scale: dict[str, float]


class CapitalUnlockManager:
    """Rebalances entry budgets away from stuck symbols while keeping scanning global."""

    def __init__(self, config: CapitalUnlockConfig | None = None) -> None:
        self.config = config or CapitalUnlockConfig.from_env()

    def evaluate(
        self,
        *,
        now_ts: float | None,
        base_topk: int,
        exposure_by_symbol_quote: dict[str, float],
        position_age_by_symbol_s: dict[str, float],
        stuck_symbols: set[str],
        total_capital_quote: float,
    ) -> CapitalUnlockDecision:
        now = time.time() if now_ts is None else float(now_ts)
        _ = now
        base = max(1, int(base_topk))
        if not self.config.enabled:
            return CapitalUnlockDecision(
                redirect_mode=False,
                reason="capital_unlock_disabled",
                locked_exposure_ratio=0.0,
                median_stuck_hold_s=0.0,
                recommended_topk=base,
                symbol_entry_scale={},
            )

        exp_map = {str(k).upper(): abs(float(v)) for k, v in (exposure_by_symbol_quote or {}).items()}
        stuck = {str(s).upper() for s in (stuck_symbols or set()) if str(s).strip()}
        stuck_exposure = sum(exp_map.get(sym, 0.0) for sym in stuck)
        total_cap = max(1e-9, float(total_capital_quote))
        total_exposure = sum(exp_map.values())
        denom = max(total_cap, total_exposure, 1e-9)
        locked_ratio = stuck_exposure / denom

        age_vals = [
            max(0.0, float(position_age_by_symbol_s.get(sym, 0.0) or 0.0))
            for sym in stuck
        ]
        median_hold_s = statistics.median(age_vals) if age_vals else 0.0

        by_ratio = locked_ratio >= self.config.locked_exposure_ratio_trigger
        by_hold = median_hold_s >= self.config.median_hold_s_trigger and bool(stuck)
        redirect = bool(by_ratio or by_hold)

        if redirect:
            reason = "locked_exposure_ratio" if by_ratio else "median_hold_time"
            topk = min(base, int(self.config.redirect_topk))
            scale_map = {sym: float(self.config.stuck_entry_scale) for sym in stuck}
        else:
            reason = "ok"
            topk = base
            scale_map = {}

        return CapitalUnlockDecision(
            redirect_mode=redirect,
            reason=reason,
            locked_exposure_ratio=float(locked_ratio),
            median_stuck_hold_s=float(median_hold_s),
            recommended_topk=int(topk),
            symbol_entry_scale=scale_map,
        )
