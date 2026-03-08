from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math


@dataclass
class MarketState:
    symbol: str
    ts: float
    trend_30s_bps: float
    trend_2m_bps: float
    trend_10m_bps: float
    realized_vol_2m: float
    realized_vol_10m: float
    spread_bps: float
    depth_notional: float
    liquidity_regime: str
    regime_hint: str
    confidence: float
    data_quality_score: float
    spread_spike: bool


def _pct_move_bps(old: float, new: float) -> float:
    if old <= 0.0 or new <= 0.0:
        return 0.0
    return ((new / old) - 1.0) * 10000.0


class MarketWatchService:
    def __init__(self, *, every_s: float = 30.0, maxlen: int = 2000) -> None:
        self.every_s = max(5.0, float(every_s))
        self._maxlen = max(200, int(maxlen))
        self._history: dict[str, deque[tuple[float, float]]] = {}
        self._last_emit_ts: dict[str, float] = {}

    def _series(self, symbol: str) -> deque[tuple[float, float]]:
        sym = str(symbol or "").upper()
        if sym not in self._history:
            self._history[sym] = deque(maxlen=self._maxlen)
        return self._history[sym]

    def _lookup_price(self, series: deque[tuple[float, float]], now_ts: float, horizon_s: float) -> float:
        target = float(now_ts) - float(horizon_s)
        chosen = 0.0
        for ts, px in reversed(series):
            if ts <= target:
                chosen = float(px)
                break
        if chosen <= 0.0 and series:
            chosen = float(series[0][1])
        return max(0.0, chosen)

    @staticmethod
    def _realized_vol(prices: list[float]) -> float:
        if len(prices) < 3:
            return 0.0
        rets: list[float] = []
        for i in range(1, len(prices)):
            a = float(prices[i - 1])
            b = float(prices[i])
            if a <= 0.0 or b <= 0.0:
                continue
            rets.append((b / a) - 1.0)
        if not rets:
            return 0.0
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        return math.sqrt(max(0.0, var))

    def update(
        self,
        *,
        symbol: str,
        ts: float,
        bid: float,
        ask: float,
        depth_notional: float,
        data_quality_score: float = 1.0,
        spread_spike: bool = False,
    ) -> MarketState:
        sym = str(symbol or "").upper()
        now = float(ts)
        b = max(0.0, float(bid))
        a = max(0.0, float(ask))
        mid = (a + b) / 2.0 if (a > 0.0 and b > 0.0) else 0.0
        spread_bps = 0.0 if mid <= 0.0 else max(0.0, ((a - b) / max(mid, 1e-12)) * 10000.0)
        s = self._series(sym)
        if mid > 0.0:
            s.append((now, mid))
        p30 = self._lookup_price(s, now, 30.0)
        p120 = self._lookup_price(s, now, 120.0)
        p600 = self._lookup_price(s, now, 600.0)
        trend_30 = _pct_move_bps(p30, mid)
        trend_120 = _pct_move_bps(p120, mid)
        trend_600 = _pct_move_bps(p600, mid)
        prices_2m = [px for t, px in s if t >= now - 120.0]
        prices_10m = [px for t, px in s if t >= now - 600.0]
        rv_2m = self._realized_vol(prices_2m)
        rv_10m = self._realized_vol(prices_10m)
        depth = max(0.0, float(depth_notional))
        if depth < 50.0:
            liq = "THIN"
        elif depth < 1000.0:
            liq = "NORMAL"
        else:
            liq = "DEEP"

        regime = "RANGE"
        conf = 0.45
        if spread_spike or spread_bps > 80.0 or rv_2m > 0.03:
            regime = "PANIC"
            conf = 0.75
        elif trend_120 > 20.0 and trend_30 > 5.0:
            regime = "TREND_UP"
            conf = min(0.95, 0.55 + min(0.35, abs(trend_120) / 200.0))
        elif trend_120 < -20.0 and trend_30 < -5.0:
            regime = "TREND_DOWN"
            conf = min(0.95, 0.55 + min(0.35, abs(trend_120) / 200.0))
        elif abs(trend_120) < 8.0:
            regime = "RANGE"
            conf = 0.55

        return MarketState(
            symbol=sym,
            ts=now,
            trend_30s_bps=float(trend_30),
            trend_2m_bps=float(trend_120),
            trend_10m_bps=float(trend_600),
            realized_vol_2m=float(rv_2m),
            realized_vol_10m=float(rv_10m),
            spread_bps=float(spread_bps),
            depth_notional=float(depth),
            liquidity_regime=liq,
            regime_hint=regime,
            confidence=float(max(0.0, min(1.0, conf))),
            data_quality_score=float(max(0.0, min(1.0, data_quality_score))),
            spread_spike=bool(spread_spike),
        )

    def should_emit(self, *, symbol: str, now_ts: float) -> bool:
        sym = str(symbol or "").upper()
        last = float(self._last_emit_ts.get(sym, 0.0) or 0.0)
        if float(now_ts) - last < self.every_s:
            return False
        self._last_emit_ts[sym] = float(now_ts)
        return True

