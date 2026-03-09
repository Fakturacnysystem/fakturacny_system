from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import time
from typing import Any, Mapping

from autonomous_investment_robot.services.distributed.compute_bridge import (
    DistributedRanking,
    LocalComputeBridge,
)
from autonomous_investment_robot.services.distributed.contracts import (
    DEFAULT_PAYLOAD_VERSION,
    DistributedEnvelope,
    DistributedStreamNames,
    decode_stream_entry,
    encode_stream_entry,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ComputeWorkerConfig:
    redis_url: str
    stream_prefix: str = "autobot"
    payload_version: str = DEFAULT_PAYLOAD_VERSION
    block_ms: int = 1000
    idle_sleep_s: float = 0.2
    maxlen: int = 5000

    @classmethod
    def from_env(cls) -> "ComputeWorkerConfig":
        return cls(
            redis_url=str(os.getenv("AUTONOMOUS_REDIS_URL", "") or os.getenv("REDIS_URL", "") or "").strip(),
            stream_prefix=str(os.getenv("AUTONOMOUS_STREAM_PREFIX", "autobot") or "autobot").strip(),
            payload_version=str(os.getenv("AUTONOMOUS_STREAM_PAYLOAD_VERSION", DEFAULT_PAYLOAD_VERSION) or DEFAULT_PAYLOAD_VERSION),
            block_ms=max(50, int(float(os.getenv("AUTONOMOUS_COMPUTE_WORKER_BLOCK_MS", "800") or "800"))),
            idle_sleep_s=max(0.05, float(os.getenv("AUTONOMOUS_COMPUTE_WORKER_IDLE_SLEEP_S", "0.2") or "0.2")),
            maxlen=max(100, int(float(os.getenv("AUTONOMOUS_COMPUTE_STREAM_MAXLEN", "5000") or "5000"))),
        )


class RedisComputeWorker:
    """Compute-side worker consuming scan tasks and publishing ranking results."""

    def __init__(self, config: ComputeWorkerConfig) -> None:
        self.config = config
        self.streams = DistributedStreamNames.from_prefix(config.stream_prefix)
        self.local_bridge = LocalComputeBridge()
        self._client = None
        self._last_id = "$"
        self._seen_idempotency: set[str] = set()
        self._last_error = ""

    def connect(self) -> dict[str, Any]:
        try:
            import redis  # type: ignore
        except Exception as exc:
            self._last_error = f"dependency_missing:redis:{exc}"
            return {"ok": False, "reason": self._last_error}
        try:
            self._client = redis.Redis.from_url(self.config.redis_url, decode_responses=False)
            self._client.ping()
            self._last_error = ""
            return {"ok": True, "reason": "ok"}
        except Exception as exc:
            self._client = None
            self._last_error = str(exc)
            return {"ok": False, "reason": self._last_error}

    @property
    def ready(self) -> bool:
        return self._client is not None

    def health(self) -> dict[str, Any]:
        return {
            "ok": bool(self.ready),
            "redis_url_set": bool(self.config.redis_url),
            "stream_prefix": self.config.stream_prefix,
            "task_stream": self.streams.task_scan,
            "result_stream": self.streams.result_rankings,
            "error": self._last_error,
            "ts": _utc_now_iso(),
        }

    def _decode_rows(self, rows: list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]) -> list[DistributedEnvelope]:
        out: list[DistributedEnvelope] = []
        for _, records in rows:
            for msg_id, fields in records:
                try:
                    env = decode_stream_entry(
                        {
                            (k.decode("utf-8", errors="ignore") if isinstance(k, bytes) else str(k)): v
                            for k, v in dict(fields).items()
                        }
                    )
                except Exception:
                    continue
                out.append(env)
                self._last_id = msg_id.decode("utf-8", errors="ignore") if isinstance(msg_id, bytes) else str(msg_id)
        return out

    def _publish_ranking_result(
        self,
        *,
        task: DistributedEnvelope,
        rankings: Mapping[str, DistributedRanking],
    ) -> None:
        if not self.ready:
            return
        payload = {
            "kind": "scan_rank_result",
            "task_id": task.task_id,
            "rankings": [row.to_dict() for row in rankings.values()],
            "worker_ts": time.time(),
            "worker_host": str(os.getenv("HOSTNAME", "") or ""),
        }
        response = DistributedEnvelope(
            task_id=task.task_id,
            run_id=task.run_id,
            symbol=task.symbol,
            market_class=task.market_class,
            ts=time.time(),
            ttl_s=max(2.0, task.ttl_s),
            payload_version=self.config.payload_version,
            idempotency_key=task.idempotency_key,
            payload=payload,
        )
        self._client.xadd(  # type: ignore[union-attr]
            self.streams.result_rankings,
            encode_stream_entry(response),
            maxlen=int(self.config.maxlen),
            approximate=True,
        )

    def _handle_scan_task(self, task: DistributedEnvelope) -> None:
        payload = task.payload if isinstance(task.payload, dict) else {}
        symbols_raw = payload.get("symbols", [])
        if not isinstance(symbols_raw, list):
            return
        symbols = [str(x).strip() for x in symbols_raw if str(x).strip()]
        if not symbols:
            return
        market_map_raw = payload.get("market_class_by_symbol", {})
        market_map = market_map_raw if isinstance(market_map_raw, Mapping) else {}
        top_n = max(1, int(float(payload.get("top_n", len(symbols)) or len(symbols))))
        result = self.local_bridge.request_rankings(
            run_id=task.run_id,
            symbols=symbols,
            market_class_by_symbol={str(k): str(v) for k, v in market_map.items()},
            top_n=top_n,
            timeout_s=min(1.0, max(0.1, task.ttl_s / 2.0)),
        )
        self._publish_ranking_result(task=task, rankings=result.rankings)

    def poll_once(self) -> dict[str, Any]:
        if not self.ready:
            return {"status": "error", "reason": "not_connected"}
        try:
            rows = self._client.xread(  # type: ignore[union-attr]
                {self.streams.task_scan: self._last_id},
                count=32,
                block=int(self.config.block_ms),
            )
        except Exception as exc:
            self._last_error = str(exc)
            return {"status": "error", "reason": f"read_failed:{exc}"}
        if not rows:
            return {"status": "idle", "reason": "no_tasks"}
        processed = 0
        skipped = 0
        for env in self._decode_rows(rows):
            if not env.task_id:
                skipped += 1
                continue
            if env.idempotency_key and env.idempotency_key in self._seen_idempotency:
                skipped += 1
                continue
            if env.idempotency_key:
                self._seen_idempotency.add(env.idempotency_key)
            if env.expired:
                skipped += 1
                continue
            kind = str((env.payload or {}).get("kind", "") or "").strip().lower()
            if kind in {"scan_rank", "scan"}:
                self._handle_scan_task(env)
                processed += 1
            else:
                skipped += 1
        return {"status": "ok", "processed": processed, "skipped": skipped}

    def run_forever(self, *, run_dir: str) -> None:
        out_path = os.path.join(run_dir, "compute_worker.log")
        os.makedirs(run_dir, exist_ok=True)
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "event": "compute_worker_start", "health": self.health()}, sort_keys=True) + "\n")
            while True:
                row = self.poll_once()
                if row.get("status") == "error":
                    fh.write(json.dumps({"ts": time.time(), "event": "compute_worker_error", **row}, sort_keys=True) + "\n")
                    fh.flush()
                    time.sleep(max(self.config.idle_sleep_s, 1.0))
                    continue
                if row.get("status") == "ok":
                    fh.write(json.dumps({"ts": time.time(), "event": "compute_worker_tick", **row}, sort_keys=True) + "\n")
                    fh.flush()
                time.sleep(self.config.idle_sleep_s)
