from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class WSStreamLimits:
    max_subscribe_msgs_per_s: int = 5
    max_streams_per_conn: int = 200
    reconnect_before_s: int = 23 * 3600


@dataclass
class MarketStreamEvent:
    stream: str
    event_type: str
    symbol: str
    event_time_ms: int
    payload: dict[str, Any]


@dataclass
class StreamHealth:
    reconnects: int = 0
    last_event_ms: int = 0
    started_at_s: float = field(default_factory=time.time)

    def should_rotate(self, now_s: float, limits: WSStreamLimits) -> bool:
        return (now_s - self.started_at_s) >= limits.reconnect_before_s


class BinanceWSStreams:
    def __init__(
        self,
        ws_base_url: str,
        symbols: list[str],
        run_dir: str,
        limits: WSStreamLimits | None = None,
    ) -> None:
        self.ws_base_url = ws_base_url.rstrip("/")
        self.symbols = [s.lower() for s in symbols]
        self.limits = limits or WSStreamLimits()
        self.health = StreamHealth()
        self.run_dir = Path(run_dir)
        self.record_dir = self.run_dir / "recordings"
        self.record_dir.mkdir(parents=True, exist_ok=True)

    def stream_names(self) -> list[str]:
        streams: list[str] = []
        for symbol in self.symbols:
            streams.extend([f"{symbol}@aggTrade", f"{symbol}@bookTicker", f"{symbol}@markPrice@1s"])
        if len(streams) > self.limits.max_streams_per_conn:
            raise ValueError("Too many Binance streams configured")
        return streams

    def combined_stream_url(self) -> str:
        return f"{self.ws_base_url}/stream?streams={'/'.join(self.stream_names())}"

    def normalize_message(self, raw: dict[str, Any]) -> MarketStreamEvent:
        stream = raw.get("stream", "")
        data = raw.get("data", raw)
        et = data.get("e", "unknown")
        symbol = data.get("s", "").upper()
        evt = int(data.get("E", data.get("T", 0)))
        self.health.last_event_ms = max(self.health.last_event_ms, evt)
        return MarketStreamEvent(stream=stream, event_type=et, symbol=symbol, event_time_ms=evt, payload=data)

    def record_event(self, run_id: str, raw: dict[str, Any]) -> None:
        base = self.record_dir / run_id
        base.mkdir(parents=True, exist_ok=True)
        market = base / "market.jsonl"
        index = base / "market.index.json"

        with market.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(raw, sort_keys=True, default=str) + "\n")

        idx = {"events": 0}
        if index.exists():
            idx = json.loads(index.read_text(encoding="utf-8"))
        idx["events"] = int(idx.get("events", 0)) + 1
        index.write_text(json.dumps(idx, sort_keys=True), encoding="utf-8")

    def replay_events(self, run_id: str) -> Iterator[MarketStreamEvent]:
        market = self.record_dir / run_id / "market.jsonl"
        if not market.exists():
            return iter([])
        rows = [json.loads(line) for line in market.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            yield self.normalize_message(row)

    def detect_depth_gap(self, prev_update_id: int, next_first_id: int) -> bool:
        return next_first_id > (prev_update_id + 1)

    def reconnect_backoff_s(self, attempt: int, base_s: float = 0.5, max_s: float = 30.0) -> float:
        return min(max_s, base_s * (2**attempt))


class LiveBarBuilder:
    def __init__(self) -> None:
        self._state: dict[tuple[str, str], dict[str, float]] = {}

    def update_from_event(self, timeframe: str, event: MarketStreamEvent) -> dict[str, float]:
        key = (event.symbol, timeframe)
        state = self._state.setdefault(
            key,
            {
                "open": 0.0,
                "high": 0.0,
                "low": 0.0,
                "close": 0.0,
                "volume": 0.0,
                "mark_price": 0.0,
                "index_price": 0.0,
                "funding_rate": 0.0,
                "oi": 0.0,
                "spread_proxy": 0.0,
                "depth_notional": 0.0,
                "flow_imbalance": 0.0,
            },
        )

        payload = event.payload
        if event.event_type == "aggTrade":
            px = float(payload.get("p", 0.0))
            qty = float(payload.get("q", 0.0))
            if state["open"] == 0.0:
                state["open"] = px
                state["high"] = px
                state["low"] = px
            state["high"] = max(state["high"], px)
            state["low"] = min(state["low"], px)
            state["close"] = px
            state["volume"] += qty
            side = -1.0 if payload.get("m", False) else 1.0
            state["flow_imbalance"] += side * qty
        elif event.event_type == "bookTicker":
            bid = float(payload.get("b", 0.0))
            ask = float(payload.get("a", 0.0))
            bid_qty = float(payload.get("B", 0.0))
            ask_qty = float(payload.get("A", 0.0))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0.0
            state["spread_proxy"] = 0.0 if mid <= 0 else ((ask - bid) / mid) * 10000
            state["depth_notional"] = (bid * bid_qty) + (ask * ask_qty)
        elif event.event_type == "markPriceUpdate":
            state["mark_price"] = float(payload.get("p", 0.0))
            state["index_price"] = float(payload.get("i", 0.0))
            state["funding_rate"] = float(payload.get("r", 0.0))

        return state.copy()
