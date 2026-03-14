from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Mapping

from autonomous_investment_robot.services.distributed.contracts import (
    DEFAULT_PAYLOAD_VERSION,
    DistributedConsumerGroups,
    DistributedEnvelope,
    DistributedStreamNames,
    build_idempotency_key,
    decode_stream_entry,
    encode_stream_entry,
)
from autonomous_investment_robot.services.universe_core.cross_asset import normalize_market_class


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_score(symbol: str) -> float:
    digest = sha256(str(symbol).encode("utf-8")).hexdigest()
    return float(int(digest[:8], 16) % 1000) / 1000.0


def deterministic_shard_identity(
    *,
    run_id: str,
    symbol: str,
    contract_id: str,
    payload_version: str = DEFAULT_PAYLOAD_VERSION,
) -> str:
    raw = json.dumps(
        {
            "run_id": str(run_id),
            "symbol": str(symbol),
            "contract_id": str(contract_id),
            "payload_version": str(payload_version),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(raw.encode("utf-8")).hexdigest()[:24]


def _market_class_multiplier(market_class: str) -> float:
    cls = normalize_market_class(str(market_class or "crypto_spot"))
    if cls in {"futures", "crypto_perp"}:
        return 0.94
    if cls in {"xstock", "xstock_etf"}:
        return 0.96
    if cls in {"xstock_perp", "xstock_etf_perp"}:
        return 0.92
    if cls == "fx":
        return 0.97
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

    def _parallel_workers(self, symbol_count: int) -> int:
        requested = max(
            1,
            int(float(os.getenv("AUTONOMOUS_PARALLEL_SYMBOL_WORKERS", "4") or "4")),
        )
        return max(1, min(requested, max(1, int(symbol_count))))

    @staticmethod
    def _build_ranking(
        *,
        symbol: str,
        idx: int,
        total: int,
        market_class_by_symbol: Mapping[str, str],
    ) -> DistributedRanking:
        cls = normalize_market_class(str(market_class_by_symbol.get(symbol, "crypto_spot") or "crypto_spot"))
        base = _stable_score(symbol) * _market_class_multiplier(cls)
        rank_boost = max(0.0, 1.0 - (idx / max(total, 1)))
        score = (0.65 * base) + (0.35 * rank_boost)
        confidence = max(0.05, min(0.95, 0.35 + (score * 0.6)))
        expected_return_bps = (score - 0.5) * 32.0
        uncertainty_bps = max(5.0, 95.0 - (score * 60.0))
        return DistributedRanking(
            symbol=symbol,
            score=score,
            confidence=confidence,
            expected_return_bps=expected_return_bps,
            uncertainty_bps=uncertainty_bps,
            market_class=cls,
        )

    def health(self) -> dict[str, Any]:
        return {
            "backend": "local",
            "ok": True,
            "parallel_workers_default": self._parallel_workers(64),
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
        workers = self._parallel_workers(len(symbols))
        if workers <= 1 or len(symbols) <= 1:
            for idx, symbol in enumerate(symbols):
                rows[symbol] = self._build_ranking(
                    symbol=symbol,
                    idx=idx,
                    total=len(symbols),
                    market_class_by_symbol=market_class_by_symbol,
                )
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="local-rank") as pool:
                futures = {
                    pool.submit(
                        self._build_ranking,
                        symbol=symbol,
                        idx=idx,
                        total=len(symbols),
                        market_class_by_symbol=market_class_by_symbol,
                    ): symbol
                    for idx, symbol in enumerate(symbols)
                }
                for fut in as_completed(futures):
                    row = fut.result()
                    rows[row.symbol] = row
        return ComputeRankResponse(
            ok=True,
            source="local",
            rankings=rows,
            diagnostics={
                "run_id": str(run_id),
                "symbols": len(symbols),
                "top_n_requested": int(top_n),
                "timeout_s": float(timeout_s),
                "parallel_workers_used": int(workers),
            },
        )


class RedisComputeBridge(ComputeBridge):
    """Redis Streams bridge for live->compute ranking requests."""

    def __init__(
        self,
        *,
        redis_url: str,
        stream_names: DistributedStreamNames,
        consumer_groups: DistributedConsumerGroups | None = None,
        consumer_name: str | None = None,
        payload_version: str = DEFAULT_PAYLOAD_VERSION,
        ttl_s: float = 5.0,
    ) -> None:
        self.redis_url = str(redis_url or "").strip()
        self.stream_names = stream_names
        self.consumer_groups = consumer_groups or DistributedConsumerGroups.from_env()
        self.consumer_name = str(consumer_name or f"live-{os.getpid()}-{uuid.uuid4().hex[:8]}").strip()
        self.payload_version = str(payload_version or DEFAULT_PAYLOAD_VERSION)
        self.ttl_s = max(0.5, float(ttl_s))
        self._publish_dedupe: set[str] = set()
        self._client = None
        self._client_error = ""
        self._groups_ready = False

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
            self._groups_ready = False
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
            "consumer_groups": {
                "live_node": self.consumer_groups.live_node,
                "compute_node": self.consumer_groups.compute_node,
            },
            "consumer_name": self.consumer_name,
            "ts": _utc_now_iso(),
        }

    def _ensure_groups(self, client: Any) -> None:
        if self._groups_ready:
            return
        group_defs = (
            (self.stream_names.task_scan, self.consumer_groups.compute_node),
            (self.stream_names.result_rankings, self.consumer_groups.live_node),
            (self.stream_names.result_signals, self.consumer_groups.live_node),
            (self.stream_names.audit_events, self.consumer_groups.live_node),
        )
        for stream_name, group_name in group_defs:
            try:
                client.xgroup_create(stream_name, group_name, id="$", mkstream=True)
            except Exception as exc:
                if "BUSYGROUP" not in str(exc):
                    # Group create failures are surfaced via health/error but remain non-fatal for fallback.
                    self._client_error = f"group_init_failed:{stream_name}:{group_name}:{exc}"
        self._groups_ready = True

    def _decode_messages(
        self,
        messages: list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]],
    ) -> list[tuple[str, DistributedEnvelope]]:
        out: list[tuple[str, DistributedEnvelope]] = []
        for _, rows in messages:
            for msg_id, fields in rows:
                mapped: dict[str, Any] = {}
                for key, value in dict(fields).items():
                    if isinstance(key, bytes):
                        k = key.decode("utf-8", errors="ignore")
                    else:
                        k = str(key)
                    mapped[k] = value
                row_id = msg_id.decode("utf-8", errors="ignore") if isinstance(msg_id, bytes) else str(msg_id)
                out.append((row_id, decode_stream_entry(mapped)))
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
        self._ensure_groups(client)

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
        matched: DistributedEnvelope | None = None
        matched_msg_id = ""
        poll_ms = 120
        while time.time() < deadline:
            remaining_ms = max(1, int((deadline - time.time()) * 1000.0))
            try:
                rows = client.xreadgroup(
                    self.consumer_groups.live_node,
                    self.consumer_name,
                    {self.stream_names.result_rankings: ">"},
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
            for row_id, msg in decoded:
                if msg.task_id == task_id:
                    matched = msg
                    matched_msg_id = row_id
                    try:
                        client.xack(
                            self.stream_names.result_rankings,
                            self.consumer_groups.live_node,
                            row_id,
                        )
                    except Exception:
                        pass
                    break
                # Unmatched rows are acknowledged to avoid stale pending growth.
                try:
                    client.xack(
                        self.stream_names.result_rankings,
                        self.consumer_groups.live_node,
                        row_id,
                    )
                except Exception:
                    pass
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
                    "consumer_group": self.consumer_groups.live_node,
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
                "consumer_group": self.consumer_groups.live_node,
                "message_id": matched_msg_id,
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
    groups = DistributedConsumerGroups.from_env(
        live_node=str(os.getenv("AUTONOMOUS_CONSUMER_GROUP_LIVE_NODE", "live_node") or "live_node"),
        compute_node=str(os.getenv("AUTONOMOUS_CONSUMER_GROUP_COMPUTE_NODE", "compute_node") or "compute_node"),
    )
    consumer_name = str(os.getenv("AUTONOMOUS_CONSUMER_NAME", "") or "").strip() or None

    if backend == "local":
        return LocalComputeBridge()
    if backend == "redis":
        return RedisComputeBridge(
            redis_url=redis_url,
            stream_names=DistributedStreamNames.from_prefix(stream_prefix),
            consumer_groups=groups,
            consumer_name=consumer_name,
            payload_version=payload_version,
            ttl_s=ttl_s,
        )
    if backend == "disabled":
        return LocalComputeBridge()

    if redis_url:
        return RedisComputeBridge(
            redis_url=redis_url,
            stream_names=DistributedStreamNames.from_prefix(stream_prefix),
            consumer_groups=groups,
            consumer_name=consumer_name,
            payload_version=payload_version,
            ttl_s=ttl_s,
        )
    return LocalComputeBridge()
