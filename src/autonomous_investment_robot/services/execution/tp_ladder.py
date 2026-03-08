from __future__ import annotations

from dataclasses import dataclass
import os


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass
class TPLadderConfig:
    enabled: bool = True
    after_costs: bool = True
    t1_s: float = 600.0
    t1_pct: float = 1.5
    t2_s: float = 1200.0
    t2_pct: float = 1.0
    t3_s: float = 1800.0
    t3_pct: float = 0.7
    t4_s: float = 2400.0
    t4_pct: float = 0.5
    t5_s: float = 3600.0
    t5_pct: float = 0.35
    greedy_enabled: bool = True
    greedy_base_extra_pct: float = 0.75
    greedy_trend_extra_pct: float = 1.25
    greedy_conf_weight: float = 0.8
    greedy_toxicity_cutoff: float = 0.65
    greedy_max_pct: float = 6.0
    trail_enabled: bool = True
    trail_start_pct: float = 2.5
    trail_giveback_pct: float = 0.7

    @classmethod
    def from_env(cls) -> TPLadderConfig:
        return cls(
            enabled=_bool_env("AUTONOMOUS_TP_LADDER_ENABLED", False),
            after_costs=_bool_env("AUTONOMOUS_TP_LADDER_AFTER_COSTS", True),
            t1_s=max(0.0, _float_env("AUTONOMOUS_TP_T1_S", 600.0)),
            t1_pct=max(0.0, _float_env("AUTONOMOUS_TP_T1_PCT", 1.5)),
            t2_s=max(0.0, _float_env("AUTONOMOUS_TP_T2_S", 1200.0)),
            t2_pct=max(0.0, _float_env("AUTONOMOUS_TP_T2_PCT", 1.0)),
            t3_s=max(0.0, _float_env("AUTONOMOUS_TP_T3_S", 1800.0)),
            t3_pct=max(0.0, _float_env("AUTONOMOUS_TP_T3_PCT", 0.7)),
            t4_s=max(0.0, _float_env("AUTONOMOUS_TP_T4_S", 2400.0)),
            t4_pct=max(0.0, _float_env("AUTONOMOUS_TP_T4_PCT", 0.5)),
            t5_s=max(0.0, _float_env("AUTONOMOUS_TP_T5_S", 3600.0)),
            t5_pct=max(0.0, _float_env("AUTONOMOUS_TP_T5_PCT", 0.35)),
            greedy_enabled=_bool_env("AUTONOMOUS_TP_GREEDY_ENABLED", False),
            greedy_base_extra_pct=max(0.0, _float_env("AUTONOMOUS_TP_GREEDY_BASE_EXTRA_PCT", 0.75)),
            greedy_trend_extra_pct=max(0.0, _float_env("AUTONOMOUS_TP_GREEDY_TREND_EXTRA_PCT", 1.25)),
            greedy_conf_weight=_clamp(_float_env("AUTONOMOUS_TP_GREEDY_CONF_WEIGHT", 0.8), 0.0, 1.0),
            greedy_toxicity_cutoff=_clamp(_float_env("AUTONOMOUS_TP_GREEDY_TOXICITY_CUTOFF", 0.65), 0.0, 1.0),
            greedy_max_pct=max(0.0, _float_env("AUTONOMOUS_TP_GREEDY_MAX_PCT", 6.0)),
            trail_enabled=_bool_env("AUTONOMOUS_TP_TRAIL_ENABLED", True),
            trail_start_pct=max(0.0, _float_env("AUTONOMOUS_TP_TRAIL_START_PCT", 2.5)),
            trail_giveback_pct=max(0.0, _float_env("AUTONOMOUS_TP_TRAIL_GIVEBACK_PCT", 0.7)),
        )


def ladder_floor_tp_pct(hold_s: float, cfg: TPLadderConfig, baseline_pct: float = 2.0) -> float:
    h = max(0.0, float(hold_s))
    floor = max(0.0, float(baseline_pct))
    if not cfg.enabled:
        return floor
    if h >= cfg.t5_s:
        floor = cfg.t5_pct
    elif h >= cfg.t4_s:
        floor = cfg.t4_pct
    elif h >= cfg.t3_s:
        floor = cfg.t3_pct
    elif h >= cfg.t2_s:
        floor = cfg.t2_pct
    elif h >= cfg.t1_s:
        floor = cfg.t1_pct
    return max(float(cfg.t5_pct), float(floor))


def desired_tp_pct(
    *,
    hold_s: float,
    baseline_pct: float,
    cfg: TPLadderConfig,
    confidence: float = 0.0,
    regime: str = "",
    toxicity_score: float = 0.0,
    peak_profit_pct: float = 0.0,
) -> float:
    floor = ladder_floor_tp_pct(hold_s, cfg, baseline_pct)
    desired = float(floor)
    if cfg.greedy_enabled and float(toxicity_score) <= float(cfg.greedy_toxicity_cutoff):
        extra = float(cfg.greedy_base_extra_pct)
        trend = str(regime or "").strip().lower() in {"trend", "trending", "strong_trend"}
        if trend or float(confidence) >= 0.6:
            extra += float(cfg.greedy_trend_extra_pct) * _clamp(float(confidence), 0.0, 1.0) * float(cfg.greedy_conf_weight)
        desired = _clamp(floor + extra, floor, max(floor, cfg.greedy_max_pct))
    if cfg.trail_enabled and float(peak_profit_pct) >= float(cfg.trail_start_pct):
        trailing_floor = max(floor, float(peak_profit_pct) - float(cfg.trail_giveback_pct))
        desired = max(desired, trailing_floor)
    return max(floor, desired)
