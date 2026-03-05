from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import time
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class StreamState:
    last_update_ts: float = 0.0
    last_seq: float | None = None
    updates: int = 0
    duplicates: int = 0
    out_of_order: int = 0


class WSDataIntegrityGuard:
    """Tracks WS stream freshness, dedupe and sequencing sanity."""

    def __init__(
        self,
        *,
        stale_after_s: float = 20.0,
        max_out_of_order: int = 8,
        trade_id_cache_size: int = 10000,
    ) -> None:
        self.stale_after_s = max(0.5, float(stale_after_s))
        self.max_out_of_order = max(1, int(max_out_of_order))
        self._states: dict[str, StreamState] = {}
        self._seen_trade_ids: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=max(64, int(trade_id_cache_size))))
        self._seen_trade_lookup: dict[str, set[str]] = defaultdict(set)

    def _state(self, stream: str) -> StreamState:
        key = str(stream or "unknown")
        return self._states.setdefault(key, StreamState())

    def record_stream_update(self, *, stream: str, ts: float, seq: float | None = None) -> None:
        state = self._state(stream)
        new_ts = _safe_float(ts, 0.0)
        if new_ts > 0.0 and state.last_update_ts > 0.0 and new_ts < state.last_update_ts:
            state.out_of_order += 1
        if seq is not None and state.last_seq is not None and float(seq) <= float(state.last_seq):
            state.out_of_order += 1
        if new_ts > 0.0:
            state.last_update_ts = max(state.last_update_ts, new_ts)
        if seq is not None:
            state.last_seq = float(seq)
        state.updates += 1

    def record_trade(self, *, stream: str, trade_id: str, ts: float, seq: float | None = None) -> bool:
        key = str(stream or "unknown")
        tid = str(trade_id or "").strip()
        if not tid:
            self.record_stream_update(stream=key, ts=ts, seq=seq)
            return True
        lookup = self._seen_trade_lookup[key]
        if tid in lookup:
            self._state(key).duplicates += 1
            return False
        fifo = self._seen_trade_ids[key]
        fifo.append(tid)
        lookup.add(tid)
        while len(lookup) > fifo.maxlen and fifo:
            old = fifo.popleft()
            lookup.discard(old)
        self.record_stream_update(stream=key, ts=ts, seq=seq)
        return True

    def observe_cycle(
        self,
        *,
        quotes: list[Any],
        quality: dict[str, Any] | None = None,
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        now = time.time() if now_ts is None else float(now_ts)
        for quote in quotes or []:
            venue = str(getattr(quote, "venue", "unknown") or "unknown")
            ts = _safe_float(getattr(quote, "ts", now), now)
            self.record_stream_update(stream=venue, ts=ts, seq=None)
        if isinstance(quality, dict):
            for venue, row in quality.items():
                if not isinstance(row, dict):
                    continue
                ts = _safe_float(row.get("ts", now), now)
                seq = row.get("seq")
                self.record_stream_update(stream=str(venue), ts=ts, seq=_safe_float(seq) if seq is not None else None)
        return self.snapshot(now_ts=now)

    def snapshot(self, *, now_ts: float | None = None) -> dict[str, Any]:
        now = time.time() if now_ts is None else float(now_ts)
        streams: dict[str, Any] = {}
        healthy = True
        for name, state in self._states.items():
            age = float("inf") if state.last_update_ts <= 0.0 else max(0.0, now - state.last_update_ts)
            stale = age > self.stale_after_s
            out_of_order = state.out_of_order > self.max_out_of_order
            if stale or out_of_order:
                healthy = False
            streams[name] = {
                "age_s": age,
                "stale": stale,
                "updates": state.updates,
                "duplicates": state.duplicates,
                "out_of_order": state.out_of_order,
                "out_of_order_exceeded": out_of_order,
            }
        if not streams:
            healthy = False
        return {
            "healthy": healthy,
            "streams": streams,
            "stale_after_s": self.stale_after_s,
            "max_out_of_order": self.max_out_of_order,
            "ts": now,
        }

    def healthy(self, *, now_ts: float | None = None) -> bool:
        snap = self.snapshot(now_ts=now_ts)
        return bool(snap.get("healthy", False))
