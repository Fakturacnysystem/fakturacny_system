from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import time


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(max(0, min(len(ordered) - 1, round((len(ordered) - 1) * max(0.0, min(1.0, q))))))
    return float(ordered[idx])


@dataclass
class SlippageCalibration:
    market: str
    samples: int
    percentile: float
    value_bps: float
    min_bps: float
    max_bps: float
    updated_ts: float


class SlippageCalibrator:
    """Rolling slippage percentile calibrator for ProfitGate floors."""

    def __init__(
        self,
        *,
        percentile: float = 0.95,
        min_bps: float = 10.0,
        max_bps: float = 60.0,
        default_spot_bps: float = 15.0,
        default_perps_bps: float = 20.0,
        window_size: int = 2000,
    ) -> None:
        self.percentile = max(0.5, min(0.999, float(percentile)))
        self.min_bps = max(0.1, float(min_bps))
        self.max_bps = max(self.min_bps, float(max_bps))
        self._samples_spot: deque[float] = deque(maxlen=max(32, int(window_size)))
        self._samples_perps: deque[float] = deque(maxlen=max(32, int(window_size)))
        self._spot_bps = float(max(self.min_bps, min(self.max_bps, default_spot_bps)))
        self._perps_bps = float(max(self.min_bps, min(self.max_bps, default_perps_bps)))
        self._last_update_ts = 0.0

    def _bucket(self, market: str) -> deque[float]:
        return self._samples_perps if str(market).strip().lower() == "perps" else self._samples_spot

    def observe_bps(self, *, bps: float, market: str = "spot", ts: float | None = None) -> None:
        val = abs(_safe_float(bps, 0.0))
        if not math.isfinite(val) or val <= 0.0:
            return
        self._bucket(market).append(val)
        self._last_update_ts = time.time() if ts is None else float(ts)

    def observe_fill(
        self,
        *,
        side: str,
        fill_price: float,
        mid_at_submit: float,
        market: str = "spot",
        ts: float | None = None,
    ) -> None:
        mid = _safe_float(mid_at_submit, 0.0)
        px = _safe_float(fill_price, 0.0)
        if mid <= 0.0 or px <= 0.0:
            return
        side_n = str(side).strip().lower()
        if side_n == "buy":
            # Positive adverse slippage if buy filled above mid.
            raw = ((px - mid) / mid) * 10000.0
        else:
            # Positive adverse slippage if sell filled below mid.
            raw = ((mid - px) / mid) * 10000.0
        self.observe_bps(bps=max(0.0, raw), market=market, ts=ts)

    def recalibrate(self, *, market: str = "spot") -> SlippageCalibration:
        bucket = list(self._bucket(market))
        if len(bucket) >= 8:
            pctl = _quantile(bucket, self.percentile)
            val = max(self.min_bps, min(self.max_bps, pctl))
        else:
            val = self._perps_bps if str(market).strip().lower() == "perps" else self._spot_bps
        if str(market).strip().lower() == "perps":
            self._perps_bps = float(val)
        else:
            self._spot_bps = float(val)
        stamp = time.time()
        self._last_update_ts = max(self._last_update_ts, stamp)
        return SlippageCalibration(
            market=str(market).strip().lower() or "spot",
            samples=len(bucket),
            percentile=self.percentile,
            value_bps=float(val),
            min_bps=self.min_bps,
            max_bps=self.max_bps,
            updated_ts=stamp,
        )

    def calibrated_bps(self, *, market: str = "spot") -> float:
        if str(market).strip().lower() == "perps":
            return float(self._perps_bps)
        return float(self._spot_bps)

    def snapshot(self) -> dict[str, float]:
        return {
            "spot_bps": float(self._spot_bps),
            "perps_bps": float(self._perps_bps),
            "percentile": float(self.percentile),
            "min_bps": float(self.min_bps),
            "max_bps": float(self.max_bps),
            "samples_spot": float(len(self._samples_spot)),
            "samples_perps": float(len(self._samples_perps)),
            "last_update_ts": float(self._last_update_ts),
        }
