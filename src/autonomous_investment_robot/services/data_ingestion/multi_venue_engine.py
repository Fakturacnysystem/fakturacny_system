from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import sqrt
from pathlib import Path
import time
from typing import Any


@dataclass
class VenueQuote:
    venue: str
    symbol: str
    bid: float
    ask: float
    depth_notional: float
    ts: float
    latency_ms: float = 0.0
    level: str = "L2"
    source: str = "ws"

    @property
    def mid(self) -> float:
        if self.bid <= 0.0 or self.ask <= 0.0:
            return 0.0
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        m = self.mid
        if m <= 0.0:
            return 0.0
        return ((self.ask - self.bid) / m) * 10000.0


@dataclass
class FeedQuality:
    venue: str
    symbol: str
    score: float
    stale: bool
    clock_drift_ms: float
    reasons: list[str]


class MultiVenueMarketDataEngine:
    def __init__(self, run_dir: str, stale_after_s: float = 4.0, max_clock_drift_ms: float = 500.0) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.ticks_dir = self.run_dir / "ticks"
        self.ticks_dir.mkdir(parents=True, exist_ok=True)
        self.stale_after_s = max(0.2, float(stale_after_s))
        self.max_clock_drift_ms = max(1.0, float(max_clock_drift_ms))
        self.clock_offsets_ms: dict[str, float] = {}

    def normalize_symbol(self, symbol: str) -> str:
        return "".join(ch for ch in symbol.upper() if ch.isalnum())

    def update_clock_drift(self, venue: str, venue_ts_ms: float, now_ts: float | None = None) -> float:
        now_ts = time.time() if now_ts is None else float(now_ts)
        drift = float(venue_ts_ms) - now_ts * 1000.0
        self.clock_offsets_ms[venue] = drift
        return drift

    def score_quote(self, quote: VenueQuote, now_ts: float | None = None) -> FeedQuality:
        now_ts = time.time() if now_ts is None else float(now_ts)
        reasons: list[str] = []
        score = 100.0
        stale = (now_ts - quote.ts) > self.stale_after_s
        if stale:
            reasons.append("stale_feed")
            score -= 45.0
        if quote.bid <= 0.0 or quote.ask <= 0.0 or quote.ask <= quote.bid:
            reasons.append("invalid_book")
            score -= 80.0
        spread_bps = max(0.0, quote.spread_bps)
        if spread_bps > 0.0:
            score -= min(45.0, spread_bps * 1.5)
        if quote.latency_ms > 0.0:
            score -= min(25.0, quote.latency_ms / 15.0)
        if quote.depth_notional > 0.0:
            score += min(12.0, sqrt(quote.depth_notional) / 80.0)
        drift = float(self.clock_offsets_ms.get(quote.venue, 0.0))
        drift_abs = abs(drift)
        if drift_abs > self.max_clock_drift_ms:
            reasons.append("clock_drift_high")
            score -= min(30.0, (drift_abs - self.max_clock_drift_ms) / 20.0)
        if quote.level == "L3":
            score += 3.0
        elif quote.level == "L1":
            score -= 5.0
        if quote.source == "rest_fallback":
            reasons.append("rest_fallback")
            score -= 8.0
        if not reasons:
            reasons.append("healthy")
        score = max(0.0, min(100.0, score))
        return FeedQuality(
            venue=quote.venue,
            symbol=quote.symbol,
            score=score,
            stale=stale,
            clock_drift_ms=drift,
            reasons=reasons,
        )

    def choose_best_quote(self, quotes: list[VenueQuote], now_ts: float | None = None) -> tuple[VenueQuote | None, dict[str, FeedQuality]]:
        now_ts = time.time() if now_ts is None else float(now_ts)
        if not quotes:
            return None, {}
        quality = {q.venue: self.score_quote(q, now_ts=now_ts) for q in quotes}
        ranked = sorted(
            quotes,
            key=lambda q: (
                quality[q.venue].score,
                -max(0.0, q.spread_bps),
                q.depth_notional,
            ),
            reverse=True,
        )
        best = ranked[0]
        return best, quality

    def choose_with_fallback(
        self,
        primary_venue: str,
        quotes: list[VenueQuote],
        now_ts: float | None = None,
        min_primary_score: float = 30.0,
    ) -> tuple[VenueQuote | None, dict[str, FeedQuality], bool]:
        best, quality = self.choose_best_quote(quotes, now_ts=now_ts)
        if best is None:
            return None, quality, False
        q_primary = next((q for q in quotes if q.venue == primary_venue), None)
        if q_primary is None:
            return best, quality, best.venue != primary_venue
        primary_quality = quality.get(primary_venue, self.score_quote(q_primary))
        if primary_quality.score >= min_primary_score and not primary_quality.stale:
            return q_primary, quality, False
        return best, quality, best.venue != primary_venue

    def collect_quotes(self, symbol: str, connectors: dict[str, Any]) -> list[VenueQuote]:
        out: list[VenueQuote] = []
        for venue, conn in connectors.items():
            t0 = time.time()
            try:
                if hasattr(conn, "market_snapshot"):
                    snap = conn.market_snapshot(symbol, max_age_s=1.0)
                    bid = float(snap.get("bid", 0.0) or 0.0)
                    ask = float(snap.get("ask", 0.0) or 0.0)
                    depth = float(snap.get("depth_notional", 0.0) or 0.0)
                    ts = float(snap.get("ts", t0) or t0)
                    level = str(snap.get("level", "L2") or "L2")
                    source = str(snap.get("source", "ws") or "ws")
                elif hasattr(conn, "ticker"):
                    row = conn.ticker(symbol)
                    row = row.get(symbol) if isinstance(row, dict) and symbol in row else (next(iter(row.values())) if isinstance(row, dict) and row else {})
                    bid_raw = row.get("b", 0.0) if isinstance(row, dict) else 0.0
                    ask_raw = row.get("a", 0.0) if isinstance(row, dict) else 0.0
                    bid = float(bid_raw[0] if isinstance(bid_raw, list) and bid_raw else bid_raw or 0.0)
                    ask = float(ask_raw[0] if isinstance(ask_raw, list) and ask_raw else ask_raw or 0.0)
                    depth = 0.0
                    ts = t0
                    level = "L1"
                    source = "rest_fallback"
                elif hasattr(conn, "book_ticker"):
                    row = conn.book_ticker(symbol)
                    bid = float(row.get("bidPrice", 0.0) or 0.0)
                    ask = float(row.get("askPrice", 0.0) or 0.0)
                    bq = float(row.get("bidQty", 0.0) or 0.0)
                    aq = float(row.get("askQty", 0.0) or 0.0)
                    depth = (bid * max(0.0, bq)) + (ask * max(0.0, aq))
                    ts = t0
                    level = "L1"
                    source = "rest_fallback"
                else:
                    continue
                latency_ms = max(0.0, (time.time() - t0) * 1000.0)
                out.append(
                    VenueQuote(
                        venue=venue,
                        symbol=self.normalize_symbol(symbol),
                        bid=bid,
                        ask=ask,
                        depth_notional=depth,
                        ts=ts,
                        latency_ms=latency_ms,
                        level=level,
                        source=source,
                    )
                )
            except Exception:
                continue
        return out

    def append_tick(self, quote: VenueQuote, quality: FeedQuality) -> None:
        target = self.ticks_dir / f"{quote.symbol.lower()}.jsonl"
        row = {
            "quote": asdict(quote),
            "quality": asdict(quality),
        }
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
