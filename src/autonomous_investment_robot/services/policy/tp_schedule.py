from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MarketState:
    regime_hint: str = "RANGE"
    confidence: float = 0.0
    spread_spike: bool = False


def parse_schedule(s: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    raw = str(s or "").strip()
    if not raw:
        return []
    for part in raw.split(","):
        item = part.strip()
        if not item or ":" not in item:
            continue
        left, right = item.split(":", 1)
        try:
            sec = int(float(left.strip()))
            bps = int(float(right.strip()))
        except Exception:
            continue
        if sec < 0:
            sec = 0
        if bps < 0:
            bps = 0
        out.append((sec, bps))
    out.sort(key=lambda x: x[0])
    dedup: dict[int, int] = {}
    for sec, bps in out:
        dedup[sec] = bps
    return sorted(dedup.items(), key=lambda x: x[0])


def target_gross_bps_for_hold(hold_s: int, schedule: list[tuple[int, int]]) -> int:
    if not schedule:
        return 0
    h = max(0, int(hold_s))
    chosen = schedule[0][1]
    for sec, bps in schedule:
        if h >= sec:
            chosen = bps
        else:
            break
    return int(max(0, chosen))


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_effective_sell_thresholds_bps(
    *,
    hold_s: int,
    modeled_cost_bps: float,
    entry_price: float,
    bid: float,
    market_watch: MarketState | None,
    hard_min_net_bps: int,
    schedule_str: str,
    greedy_mode: bool,
    greedy_up_net_bps: int,
    greedy_mid_net_bps: int,
    greedy_down_net_bps: int,
) -> dict[str, float]:
    _ = entry_price
    _ = bid
    hard_min_net = max(30, int(hard_min_net_bps))
    costs = max(0.0, float(modeled_cost_bps))
    schedule = parse_schedule(schedule_str)
    schedule_target_gross = target_gross_bps_for_hold(max(0, int(hold_s)), schedule)
    schedule_target_net = float(schedule_target_gross) - costs

    greedy_target_net = float(greedy_mid_net_bps)
    if greedy_mode:
        mw = market_watch or MarketState()
        regime = str(mw.regime_hint or "RANGE").strip().upper()
        conf = _clamp(float(mw.confidence), 0.0, 1.0)
        spike = bool(mw.spread_spike)
        if regime == "TREND_UP" and conf >= 0.6 and not spike:
            greedy_target_net = float(greedy_up_net_bps)
        elif regime in {"RANGE", "TREND_UP"}:
            greedy_target_net = float(greedy_mid_net_bps)
        else:
            greedy_target_net = float(greedy_down_net_bps)
    else:
        greedy_target_net = float(hard_min_net)
    effective_target_net = max(float(hard_min_net), float(schedule_target_net), float(greedy_target_net))
    effective_target_gross = float(effective_target_net) + costs
    hard_min_gross = float(hard_min_net) + costs
    return {
        "hard_min_net_bps": float(hard_min_net),
        "hard_min_gross_bps": float(hard_min_gross),
        "schedule_target_gross_bps": float(schedule_target_gross),
        "schedule_target_net_bps": float(schedule_target_net),
        "greedy_target_net_bps": float(greedy_target_net),
        "effective_target_net_bps": float(effective_target_net),
        "effective_target_gross_bps": float(effective_target_gross),
    }
