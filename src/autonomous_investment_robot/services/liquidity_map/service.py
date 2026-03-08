from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class LiquidityMapDecision:
    active: bool
    session: str
    edge_add_bps: float
    size_scale: float
    max_child_orders_override: int | None


class LiquidityMapService:
    def __init__(
        self,
        *,
        enabled: bool = True,
        night_start_hour_utc: int = 20,
        night_end_hour_utc: int = 6,
        day_edge_add_bps: float = 0.0,
        night_edge_add_bps: float = 3.0,
        day_size_scale: float = 1.0,
        night_size_scale: float = 0.7,
        day_max_child_orders: int = 3,
        night_max_child_orders: int = 1,
    ) -> None:
        self.enabled = bool(enabled)
        self.night_start_hour_utc = int(max(0, min(23, night_start_hour_utc)))
        self.night_end_hour_utc = int(max(0, min(23, night_end_hour_utc)))
        self.day_edge_add_bps = max(0.0, float(day_edge_add_bps))
        self.night_edge_add_bps = max(0.0, float(night_edge_add_bps))
        self.day_size_scale = max(0.05, min(1.0, float(day_size_scale)))
        self.night_size_scale = max(0.05, min(1.0, float(night_size_scale)))
        self.day_max_child_orders = max(1, int(day_max_child_orders))
        self.night_max_child_orders = max(1, int(night_max_child_orders))

    def _is_night(self, ts: float) -> bool:
        hour = datetime.fromtimestamp(float(ts), tz=timezone.utc).hour
        if self.night_start_hour_utc <= self.night_end_hour_utc:
            return self.night_start_hour_utc <= hour < self.night_end_hour_utc
        return hour >= self.night_start_hour_utc or hour < self.night_end_hour_utc

    def decide(self, *, ts: float) -> LiquidityMapDecision:
        if not self.enabled:
            return LiquidityMapDecision(
                active=False,
                session="disabled",
                edge_add_bps=0.0,
                size_scale=1.0,
                max_child_orders_override=None,
            )
        night = self._is_night(ts)
        if night:
            return LiquidityMapDecision(
                active=True,
                session="night",
                edge_add_bps=float(self.night_edge_add_bps),
                size_scale=float(self.night_size_scale),
                max_child_orders_override=int(self.night_max_child_orders),
            )
        return LiquidityMapDecision(
            active=True,
            session="day",
            edge_add_bps=float(self.day_edge_add_bps),
            size_scale=float(self.day_size_scale),
            max_child_orders_override=int(self.day_max_child_orders),
        )

