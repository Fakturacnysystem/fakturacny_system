from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
import time
from typing import Any


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int
    size: int
    ttl_s: float
    max_items: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": int(self.hits),
            "misses": int(self.misses),
            "size": int(self.size),
            "ttl_s": float(self.ttl_s),
            "max_items": int(self.max_items),
        }


class TTLCache:
    """Simple in-memory TTL cache with bounded size and LRU-style eviction."""

    def __init__(self, *, ttl_s: float, max_items: int = 2048) -> None:
        self.ttl_s = max(0.01, float(ttl_s))
        self.max_items = max(1, int(max_items))
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._lock = RLock()

    def _purge_expired_locked(self, *, now_ts: float) -> None:
        while self._store:
            first_key = next(iter(self._store))
            ts, _ = self._store[first_key]
            if (now_ts - ts) <= self.ttl_s:
                break
            self._store.popitem(last=False)

    def get(self, key: str) -> Any | None:
        now_ts = time.time()
        with self._lock:
            self._purge_expired_locked(now_ts=now_ts)
            row = self._store.get(str(key))
            if row is None:
                self._misses += 1
                return None
            ts, value = row
            if (now_ts - ts) > self.ttl_s:
                self._store.pop(str(key), None)
                self._misses += 1
                return None
            self._store.move_to_end(str(key), last=True)
            self._hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        now_ts = time.time()
        with self._lock:
            self._store[str(key)] = (now_ts, value)
            self._store.move_to_end(str(key), last=True)
            self._purge_expired_locked(now_ts=now_ts)
            while len(self._store) > self.max_items:
                self._store.popitem(last=False)

    def stats(self) -> CacheStats:
        with self._lock:
            self._purge_expired_locked(now_ts=time.time())
            return CacheStats(
                hits=int(self._hits),
                misses=int(self._misses),
                size=int(len(self._store)),
                ttl_s=float(self.ttl_s),
                max_items=int(self.max_items),
            )


class FeatureCache:
    """TTL cache dedicated to fused multimodal feature snapshots."""

    def __init__(self, *, ttl_s: float = 2.0, max_items: int = 2048) -> None:
        self._cache = TTLCache(ttl_s=ttl_s, max_items=max_items)

    def get(self, key: str) -> dict[str, float] | None:
        value = self._cache.get(key)
        if not isinstance(value, dict):
            return None
        out: dict[str, float] = {}
        for k, v in value.items():
            try:
                out[str(k)] = float(v)
            except Exception:
                continue
        return out

    def set(self, key: str, value: dict[str, float]) -> None:
        self._cache.set(str(key), dict(value))

    def stats(self) -> CacheStats:
        return self._cache.stats()


class SignalCache:
    """TTL cache dedicated to trade-signal outputs."""

    def __init__(self, *, ttl_s: float = 1.0, max_items: int = 4096) -> None:
        self._cache = TTLCache(ttl_s=ttl_s, max_items=max_items)

    def get(self, key: str) -> dict[str, Any] | None:
        value = self._cache.get(key)
        if not isinstance(value, dict):
            return None
        return dict(value)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._cache.set(str(key), dict(value))

    def stats(self) -> CacheStats:
        return self._cache.stats()
