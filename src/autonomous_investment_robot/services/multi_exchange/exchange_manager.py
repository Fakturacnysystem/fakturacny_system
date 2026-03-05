from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from autonomous_investment_robot.services.multi_exchange.adapters import (
    AdapterStatus,
    BinanceAdapter,
    CoinbaseAdapter,
    KrakenAdapter,
)


@dataclass
class VenueDecision:
    venue: str
    score: float
    reason: str


class ExchangeManager:
    def __init__(self, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = str(os.getenv("AUTONOMOUS_MULTIPLE_EXCHANGES_ENABLED", "false") or "false").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        self.enabled = bool(enabled)
        self.adapters = {
            "kraken": KrakenAdapter(),
            "binance": BinanceAdapter(),
            "coinbase": CoinbaseAdapter(),
        }
        self.status: dict[str, AdapterStatus] = {}

    def initialize(self) -> dict[str, AdapterStatus]:
        if not self.enabled:
            self.status = {
                name: AdapterStatus(venue=name, enabled=False, reason="multi_exchange_disabled")
                for name in self.adapters.keys()
            }
            return dict(self.status)
        self.status = {name: adapter.init() for name, adapter in self.adapters.items()}
        return dict(self.status)

    def discover_universe(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for name, adapter in self.adapters.items():
            st = self.status.get(name)
            if st is None or not st.enabled:
                continue
            try:
                rows.extend(adapter.discover_instruments())
            except Exception:
                continue
        return rows

    def route_venue(
        self,
        *,
        symbol: str,
        candidates: list[dict[str, Any]],
    ) -> VenueDecision:
        if not candidates:
            return VenueDecision(venue="", score=float("-inf"), reason="no_candidates")
        best = max(
            candidates,
            key=lambda c: float(c.get("liquidity", 0.0)) - float(c.get("fee_bps", 0.0)) - float(c.get("spread_bps", 0.0)),
        )
        score = float(best.get("liquidity", 0.0)) - float(best.get("fee_bps", 0.0)) - float(best.get("spread_bps", 0.0))
        return VenueDecision(
            venue=str(best.get("venue", "") or ""),
            score=score,
            reason=f"venue_selection:{symbol}",
        )
