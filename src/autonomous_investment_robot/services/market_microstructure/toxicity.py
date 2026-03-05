from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math


@dataclass
class ToxicityScore:
    symbol: str
    score: float
    spread_level: float
    spread_widening_rate: float
    depth_collapse: float
    vol_burst: float


class ToxicityScorer:
    def __init__(self, window: int = 32) -> None:
        self.window = max(5, int(window))
        self._series: dict[str, deque[dict[str, float]]] = {}

    def update(self, *, symbol: str, ts: float, mid: float, spread_bps: float, depth_notional: float) -> ToxicityScore:
        sym = str(symbol).upper()
        s = self._series.setdefault(sym, deque(maxlen=self.window))
        point = {
            "ts": float(ts),
            "mid": max(0.0, float(mid)),
            "spread_bps": max(0.0, float(spread_bps)),
            "depth_notional": max(0.0, float(depth_notional)),
        }
        s.append(point)
        if len(s) < 2:
            return ToxicityScore(sym, 0.0, 0.0, 0.0, 0.0, 0.0)

        latest = s[-1]
        prev = s[-2]
        dt = max(1e-6, latest["ts"] - prev["ts"])

        spread_level = min(1.0, latest["spread_bps"] / 20.0)
        spread_grad = max(0.0, (latest["spread_bps"] - prev["spread_bps"]) / dt)
        spread_widening_rate = min(1.0, spread_grad / 4.0)

        depth_prev = max(1e-9, prev["depth_notional"])
        depth_drop = max(0.0, (depth_prev - latest["depth_notional"]) / depth_prev)
        depth_collapse = min(1.0, depth_drop)

        ret_abs = 0.0
        if prev["mid"] > 1e-9:
            ret_abs = abs(latest["mid"] - prev["mid"]) / prev["mid"]
        # 35 bps one-step return saturates burst.
        vol_burst = min(1.0, ret_abs / 0.0035)

        score = (
            0.30 * spread_level
            + 0.25 * spread_widening_rate
            + 0.25 * depth_collapse
            + 0.20 * vol_burst
        )
        if math.isnan(score) or math.isinf(score):
            score = 0.0
        score = max(0.0, min(1.0, score))
        return ToxicityScore(
            symbol=sym,
            score=score,
            spread_level=spread_level,
            spread_widening_rate=spread_widening_rate,
            depth_collapse=depth_collapse,
            vol_burst=vol_burst,
        )
