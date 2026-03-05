from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass
class AdapterStatus:
    venue: str
    enabled: bool
    reason: str


class BaseExchangeAdapter:
    venue: str = "unknown"

    def __init__(self) -> None:
        self.enabled = False
        self.reason = "not_initialized"

    def init(self) -> AdapterStatus:
        raise NotImplementedError

    def discover_instruments(self) -> list[dict[str, Any]]:
        return []

    def best_quote(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "bid": 0.0, "ask": 0.0, "venue": self.venue}


class KrakenAdapter(BaseExchangeAdapter):
    venue = "kraken"

    def init(self) -> AdapterStatus:
        key = str(os.getenv("KRAKEN_API_KEY", "") or "").strip()
        secret = str(os.getenv("KRAKEN_API_SECRET", "") or "").strip()
        self.enabled = bool(key and secret)
        self.reason = "ok" if self.enabled else "missing_credentials"
        return AdapterStatus(venue=self.venue, enabled=self.enabled, reason=self.reason)


class BinanceAdapter(BaseExchangeAdapter):
    venue = "binance"

    def init(self) -> AdapterStatus:
        key = str(os.getenv("BINANCE_API_KEY", "") or "").strip()
        secret = str(os.getenv("BINANCE_API_SECRET", "") or "").strip()
        self.enabled = bool(key and secret)
        self.reason = "ok" if self.enabled else "missing_credentials"
        return AdapterStatus(venue=self.venue, enabled=self.enabled, reason=self.reason)


class CoinbaseAdapter(BaseExchangeAdapter):
    venue = "coinbase"

    def init(self) -> AdapterStatus:
        key = str(os.getenv("COINBASE_API_KEY", "") or "").strip()
        secret = str(os.getenv("COINBASE_API_SECRET", "") or "").strip()
        self.enabled = bool(key and secret)
        self.reason = "ok" if self.enabled else "missing_credentials"
        return AdapterStatus(venue=self.venue, enabled=self.enabled, reason=self.reason)
