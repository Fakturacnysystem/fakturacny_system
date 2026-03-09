from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import time
from typing import Any, Mapping

from autonomous_investment_robot.services.distributed.contracts import (
    DEFAULT_PAYLOAD_VERSION,
    DistributedEnvelope,
    DistributedStreamNames,
    build_idempotency_key,
    decode_stream_entry,
    encode_stream_entry,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_score(symbol: str) -> float:
    digest = sha256(str(symbol).encode("utf-8")).hexdigest()
    return float(int(digest[:8], 16) % 1000) / 1000.0


def _market_class_multiplier(market_class: str) -> float:
    cls = str(market_class or "crypto_spot").strip().lower()
    if cls in {"xstock", "xstock_etf"}:
        return 0.96
    if cls in {"xstock_perp", "xstock_etf_perp"}:
        return 0.92
    return 1.0


@dataclass(frozen=True)
class DistributedRanking:
    symbol: str
    score: float
    confidence: float
    expected_return_bps: float
    uncertainty_bps: float
    market_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": str(self.symbol),
            "score": float(self.score),
            "confidence": float(self.confidence),
            "expected_return_bps": float(self.expected_return_bps),
            "uncertainty_bps": float(self.uncertainty_bps),
            "market_class": str(self.market_class),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DistributedRanking":
        return cls(
            symbol=str(raw.get("symbol", "") or ""),
            score=float(raw.get("score", 0.0) or 0.0),
            confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.0) or 0.0))),
            expected_return_bps=float(raw.get("expected_return_bps", 0.0) or 0.0),
            uncertainty_bps=max(0.0, float(raw.get("uncertainty_bps", 0.0) or 0.0)),
            market_class=str(raw.get("market_class", "crypto_spot") or "crypto_spot"),
        )


@dataclass(frozen=True)
class ComputeRankResponse:
    ok: bool
    source: str
    rankings: dict[str, DistributedRanking] = field(default_factory=dict)
    error: str = ""
    stale: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def best_symbols(self, top_n: int) -> list[str]:
        rows = sorted(self.rankings.values(), key=lambda x: float(x.score), reverse=True)
        return [r.symbol for r in rows[: max(1, int(top_n))]]


class ComputeBridge:
    """Abstract live-node bridge to compute-node ranking outputs."""

    def health(self) -> dict[str, Any]:
        raise NotImplementedError

    def request_rankings(
        self,
        *,
        run_id: str,
        symbols: list[str],
        market_class_by_symbol: Mapping[str, str],
        top_n: int,
        timeout_s: float,
    ) -> ComputeRankResponse:
        raise NotImplementedError


class LocalComputeBridge(ComputeBridge):
    """Deterministic local ranking fallback used when distributed compute is unavailable."""

    def health(self) -> dict[str, Any]:
        return {
            "backend": "local",
            "ok": True,
            "ts": _utc_now_iso(),
        }

    def request_rankings(
        self,
        *,
        run_id: str,
        symbols: list[str],
        market_class_by_symbol: Mapping[str, str],
        top_n: int,
        timeout_s: float,
    ) -> ComputeRankResponse:
        rows: dict[str, DistributedRanking] = {}
        for idx, symbol in enumerate(symbols):
            cls = str(market_class_by_symbol.get(symbol, "crypto_spot") or "crypto_spot")
            base = _stable_score(symbol) * _market_class_multiplier(cls)
            rank_boost = max(0.0, 1.0 - (idx / max(len(symbols), 1)))
            score = (0.65 * base) + (0.35 * rank_boost)
            confidence = max(0.05, min(0.95, 0.35 + (score * 0.6)))
            expected_return_bps = (score - 0.5) * 32.0
            uncertainty_bps = max(5.0, 95.0 - (score * 60.0))
            rows[symbol] = DistributedRanking(
                symbol=symbol,
                score=score,
                confidence=confidence,
                expected_return_bps=expected_return_bps,
                uncertainty_bps=uncertainty_bps,
                market_class=cls,
            )
        return ComputeRankResponse(
            ok=True,
            source="local",
            rankings=rows,
            diagnostics={
                "run_id": str(run_id),
                "symbols": len(symbols),
                "top_n_requested": int(top_n),
                "timeout_s": float(timeout_s),
            },
        )


class RedisComputeBridge(ComputeBridge):
    """Redis Streams bridge for live->compute ranking requests."""

    def __init__(
        self,
        *,
        redis_url: str,
        stream_names: DistributedStreamNames,
        payload_version: str = DEFAULT_PAYLOAD_VERSION,
        ttl_s: float = 5.0,
    ) -> None:
        self.redis_url = str(redis_url or "").strip()
        self.stream_names = stream_names
        self.payload_version = str(payload_version or DEFAULT_PAYLOAD_VERSION)
        self.ttl_s = max(0.5, float(ttl_s))
        self._publish_dedupe: set[str] = set()
        self._client = None
        self._client_error = ""

    def _connect(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import redis  # type: ignore
        except Exception as exc:
            self._client_error = f"dependency_missing:redis:{exc}"
            return None
        try:
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=False)
            self._client.ping()
            self._client_error = ""
            return self._client
        except Exception as exc:
            self._client = None
            self._client_error = str(exc)
            return None

    def health(self) -> dict[str, Any]:
        client = self._connect()
        ok = bool(client is not None)
        return {
            "backend": "redis_streams",
            "ok": ok,
            "redis_url_set": bool(self.redis_url),
            "error": "" if ok else self._client_error,
            "streams": {
                "task_scan": self.stream_names.task_scan,
                "result_rankings": self.stream_names.result_rankings,
            },
            "ts": _utc_now_iso(),
        }

    def _decode_messages(self, messages: list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]) -> list[DistributedEnvelope]:
        out: list[DistributedEnvelope] = []
        for _, rows in messages:
            for _, fields in rows:
                mapped: dict[str, Any] = {}
                for key, value in dict(fields).items():
                    if isinstance(key, bytes):
                        k = key.decode("utf-8", errors="ignore")
                    else:
                        k = str(key)
                    mapped[k] = value
                out.append(decode_stream_entry(mapped))
        return out

    def request_rankings(
        self,
        *,
        run_id: str,
        symbols: list[str],
        market_class_by_symbol: Mapping[str, str],
        top_n: int,
        timeout_s: float,
    ) -> ComputeRankResponse:
        client = self._connect()
        if client is None:
            return ComputeRankResponse(
                ok=False,
                source="redis_streams",
                error=f"redis_unavailable:{self._client_error or 'unknown'}",
                stale=True,
            )

        now_ts = time.time()
        task_id = f"scan:{int(now_ts * 1000)}:{abs(hash((run_id, tuple(symbols)))) % 1000000}"
        payload: dict[str, Any] = {
            "kind": "scan_rank",
            "symbols": [str(x) for x in symbols],
            "market_class_by_symbol": {str(k): str(v) for k, v in market_class_by_symbol.items()},
            "top_n": int(max(1, top_n)),
        }
        idem = build_idempotency_key(
            stream=self.stream_names.task_scan,
            run_id=run_id,
            symbol="*",
            payload=payload,
            payload_version=self.payload_version,
        )
        if idem in self._publish_dedupe:
            return ComputeRankResponse(
                ok=False,
                source="redis_streams",
                error="idempotency_duplicate",
                stale=True,
            )
        envelope = DistributedEnvelope(
            task_id=task_id,
            run_id=str(run_id),
            symbol="*",
            market_class="mixed",
            ts=now_ts,
            ttl_s=max(self.ttl_s, float(timeout_s) * 1.5),
            payload_version=self.payload_version,
            idempotency_key=idem,
            payload=payload,
        )

        try:
            self._publish_dedupe.add(idem)
            client.xadd(self.stream_names.task_scan, encode_stream_entry(envelope), maxlen=5000, approximate=True)
        except Exception as exc:
            return ComputeRankResponse(
                ok=False,
                source="redis_streams",
                error=f"publish_failed:{exc}",
                stale=True,
            )

        deadline = time.time() + max(0.1, float(timeout_s))
        cursor = "$"
        matched: DistributedEnvelope | None = None
        poll_ms = 120
        while time.time() < deadline:
            remaining_ms = max(1, int((deadline - time.time()) * 1000.0))
            try:
                rows = client.xread(
                    {self.stream_names.result_rankings: cursor},
                    count=64,
                    block=min(poll_ms, remaining_ms),
                )
            except Exception as exc:
                return ComputeRankResponse(
                    ok=False,
                    source="redis_streams",
                    error=f"read_failed:{exc}",
                    stale=True,
                )
            if not rows:
                continue
            decoded = self._decode_messages(rows)
            for msg in decoded:
                if msg.task_id == task_id:
                    matched = msg
                    break
            if matched is not None:
                break
        if matched is None:
            return ComputeRankResponse(
                ok=False,
                source="redis_streams",
                error="timeout_waiting_for_compute_result",
                stale=True,
                diagnostics={
                    "task_id": task_id,
                    "timeout_s": float(timeout_s),
                    "symbols": len(symbols),
                },
            )

        rankings_raw = matched.payload.get("rankings", [])
        if not isinstance(rankings_raw, list):
            rankings_raw = []
        rows: dict[str, DistributedRanking] = {}
        for row in rankings_raw:
            if not isinstance(row, Mapping):
                continue
            parsed = DistributedRanking.from_mapping(row)
            if not parsed.symbol:
                continue
            rows[parsed.symbol] = parsed
        return ComputeRankResponse(
            ok=bool(rows),
            source="redis_streams",
            rankings=rows,
            stale=bool(matched.expired),
            diagnostics={
                "task_id": matched.task_id,
                "run_id": matched.run_id,
                "symbol_count": len(rows),
                "payload_version": matched.payload_version,
                "expired": bool(matched.expired),
            },
            error="" if rows else "empty_rankings_payload",
        )


def build_compute_bridge_from_env() -> ComputeBridge:
    """Build distributed bridge from env with safe local fallback."""
    backend = str(os.getenv("AUTONOMOUS_COMPUTE_BRIDGE", "auto") or "auto").strip().lower()
    redis_url = str(
        os.getenv("AUTONOMOUS_REDIS_URL", "")
        or os.getenv("REDIS_URL", "")
        or ""
    ).strip()
    stream_prefix = str(os.getenv("AUTONOMOUS_STREAM_PREFIX", "autobot") or "autobot").strip()
    payload_version = str(os.getenv("AUTONOMOUS_STREAM_PAYLOAD_VERSION", DEFAULT_PAYLOAD_VERSION) or DEFAULT_PAYLOAD_VERSION)
    ttl_s = max(0.5, float(os.getenv("AUTONOMOUS_COMPUTE_MESSAGE_TTL_S", "8.0") or "8.0"))

    if backend == "local":
        return LocalComputeBridge()
    if backend == "redis":
        return RedisComputeBridge(
            redis_url=redis_url,
            stream_names=DistributedStreamNames.from_prefix(stream_prefix),
            payload_version=payload_version,
            ttl_s=ttl_s,
        )
    if backend == "disabled":
        return LocalComputeBridge()

    if redis_url:
        return RedisComputeBridge(
            redis_url=redis_url,
            stream_names=DistributedStreamNames.from_prefix(stream_prefix),
            payload_version=payload_version,
            ttl_s=ttl_s,
        )
    return LocalComputeBridge()
