from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import time
import uuid
from typing import Any, Mapping

from autonomous_investment_robot.services.distributed.compute_bridge import (
    DistributedRanking,
    LocalComputeBridge,
)
from autonomous_investment_robot.services.distributed.contracts import (
    DEFAULT_PAYLOAD_VERSION,
    DistributedConsumerGroups,
    DistributedEnvelope,
    DistributedStreamNames,
    build_idempotency_key,
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
    consumer_group: str = "compute_node"
    consumer_name: str = ""
    live_result_group: str = "live_node"
    block_ms: int = 1000
    idle_sleep_s: float = 0.2
    maxlen: int = 5000

    @classmethod
    def from_env(cls) -> "ComputeWorkerConfig":
        return cls(
            redis_url=str(os.getenv("AUTONOMOUS_REDIS_URL", "") or os.getenv("REDIS_URL", "") or "").strip(),
            stream_prefix=str(os.getenv("AUTONOMOUS_STREAM_PREFIX", "autobot") or "autobot").strip(),
            payload_version=str(os.getenv("AUTONOMOUS_STREAM_PAYLOAD_VERSION", DEFAULT_PAYLOAD_VERSION) or DEFAULT_PAYLOAD_VERSION),
            consumer_group=str(os.getenv("AUTONOMOUS_CONSUMER_GROUP_COMPUTE_NODE", "compute_node") or "compute_node").strip() or "compute_node",
            live_result_group=str(os.getenv("AUTONOMOUS_CONSUMER_GROUP_LIVE_NODE", "live_node") or "live_node").strip() or "live_node",
            consumer_name=str(
                os.getenv("AUTONOMOUS_COMPUTE_CONSUMER_NAME", "")
                or f"compute-{os.getpid()}-{uuid.uuid4().hex[:8]}"
            ).strip(),
            block_ms=max(50, int(float(os.getenv("AUTONOMOUS_COMPUTE_WORKER_BLOCK_MS", "800") or "800"))),
            idle_sleep_s=max(0.05, float(os.getenv("AUTONOMOUS_COMPUTE_WORKER_IDLE_SLEEP_S", "0.2") or "0.2")),
            maxlen=max(100, int(float(os.getenv("AUTONOMOUS_COMPUTE_STREAM_MAXLEN", "5000") or "5000"))),
        )


class RedisComputeWorker:
    """Compute-side worker consuming scan tasks and publishing ranking results."""

    def __init__(self, config: ComputeWorkerConfig) -> None:
        self.config = config
        self.streams = DistributedStreamNames.from_prefix(config.stream_prefix)
        self.groups = DistributedConsumerGroups.from_env(
            live_node=config.live_result_group,
            compute_node=config.consumer_group,
        )
        self.local_bridge = LocalComputeBridge()
        self._client = None
        self._seen_idempotency: set[str] = set()
        self._last_error = ""
        self._groups_ready = False

    def connect(self) -> dict[str, Any]:
        try:
            import redis  # type: ignore
        except Exception as exc:
            self._last_error = f"dependency_missing:redis:{exc}"
            return {"ok": False, "reason": self._last_error}
        try:
            self._client = redis.Redis.from_url(self.config.redis_url, decode_responses=False)
            self._client.ping()
            self._ensure_groups()
            self._last_error = ""
            return {"ok": True, "reason": "ok"}
        except Exception as exc:
            self._client = None
            self._groups_ready = False
            self._last_error = str(exc)
            return {"ok": False, "reason": self._last_error}

    def _ensure_groups(self) -> None:
        if not self.ready or self._groups_ready:
            return
        assert self._client is not None
        group_defs = (
            (self.streams.task_scan, self.groups.compute_node),
            (self.streams.task_forecast, self.groups.compute_node),
            (self.streams.task_optimize, self.groups.compute_node),
            (self.streams.result_rankings, self.groups.live_node),
            (self.streams.result_signals, self.groups.live_node),
            (self.streams.audit_events, self.groups.live_node),
        )
        for stream_name, group_name in group_defs:
            try:
                self._client.xgroup_create(stream_name, group_name, id="$", mkstream=True)
            except Exception as exc:
                if "BUSYGROUP" not in str(exc):
                    self._last_error = f"group_init_failed:{stream_name}:{group_name}:{exc}"
        self._groups_ready = True

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
            "consumer_group": self.groups.compute_node,
            "consumer_name": self.config.consumer_name,
            "error": self._last_error,
            "ts": _utc_now_iso(),
        }

    def _decode_rows(
        self,
        rows: list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]],
    ) -> list[tuple[str, str, DistributedEnvelope]]:
        out: list[tuple[str, str, DistributedEnvelope]] = []
        for stream_name_raw, records in rows:
            stream_name = (
                stream_name_raw.decode("utf-8", errors="ignore")
                if isinstance(stream_name_raw, bytes)
                else str(stream_name_raw)
            )
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
                row_id = msg_id.decode("utf-8", errors="ignore") if isinstance(msg_id, bytes) else str(msg_id)
                out.append((stream_name, row_id, env))
        return out

    def _publish_result(self, *, stream: str, task: DistributedEnvelope, payload: dict[str, Any]) -> None:
        if not self.ready:
            return
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
            stream,
            encode_stream_entry(response),
            maxlen=int(self.config.maxlen),
            approximate=True,
        )

    def _publish_ranking_result(
        self,
        *,
        task: DistributedEnvelope,
        rankings: Mapping[str, DistributedRanking],
    ) -> None:
        payload = {
            "kind": "scan_rank_result",
            "task_id": task.task_id,
            "rankings": [row.to_dict() for row in rankings.values()],
            "worker_ts": time.time(),
            "worker_host": str(os.getenv("HOSTNAME", "") or ""),
        }
        self._publish_result(
            stream=self.streams.result_rankings,
            task=task,
            payload=payload,
        )

    def _publish_signal_result(self, *, task: DistributedEnvelope, rows: list[dict[str, Any]]) -> None:
        payload = {
            "kind": "forecast_result",
            "task_id": task.task_id,
            "signals": rows,
            "worker_ts": time.time(),
            "worker_host": str(os.getenv("HOSTNAME", "") or ""),
        }
        self._publish_result(
            stream=self.streams.result_signals,
            task=task,
            payload=payload,
        )

    def _publish_audit_event(self, *, event_type: str, payload: Mapping[str, Any], task: DistributedEnvelope | None = None) -> None:
        if not self.ready:
            return
        now_ts = time.time()
        base_payload = {
            "kind": "compute_audit_event",
            "event_type": str(event_type),
            "payload": dict(payload),
            "worker_ts": now_ts,
            "worker_host": str(os.getenv("HOSTNAME", "") or ""),
        }
        run_id = str(task.run_id if task is not None else "compute_node")
        symbol = str(task.symbol if task is not None else "")
        market_class = str(task.market_class if task is not None else "")
        idem = build_idempotency_key(
            stream=self.streams.audit_events,
            run_id=run_id,
            symbol=symbol or "*",
            payload=base_payload,
            payload_version=self.config.payload_version,
        )
        envelope = DistributedEnvelope(
            task_id=str(task.task_id if task is not None else f"audit:{int(now_ts * 1000)}"),
            run_id=run_id,
            symbol=symbol,
            market_class=market_class,
            ts=now_ts,
            ttl_s=60.0,
            payload_version=self.config.payload_version,
            idempotency_key=idem,
            payload=base_payload,
        )
        self._client.xadd(  # type: ignore[union-attr]
            self.streams.audit_events,
            encode_stream_entry(envelope),
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
        self._publish_audit_event(
            event_type="compute_scan_completed",
            payload={
                "task_id": task.task_id,
                "symbol_count": len(symbols),
                "top_n": top_n,
                "ok": bool(result.ok),
            },
            task=task,
        )

    def _handle_forecast_task(self, task: DistributedEnvelope) -> None:
        payload = task.payload if isinstance(task.payload, dict) else {}
        symbols_raw = payload.get("symbols", [])
        if not isinstance(symbols_raw, list):
            symbols_raw = []
        symbols = [str(x).strip() for x in symbols_raw if str(x).strip()]
        if not symbols:
            return
        market_map_raw = payload.get("market_class_by_symbol", {})
        market_map = market_map_raw if isinstance(market_map_raw, Mapping) else {}
        baseline = self.local_bridge.request_rankings(
            run_id=task.run_id,
            symbols=symbols,
            market_class_by_symbol={str(k): str(v) for k, v in market_map.items()},
            top_n=max(1, len(symbols)),
            timeout_s=min(1.0, max(0.1, task.ttl_s / 2.0)),
        )
        rows: list[dict[str, Any]] = []
        for sym, rank in baseline.rankings.items():
            rows.append(
                {
                    "symbol": str(sym),
                    "market_class": str(rank.market_class),
                    "direction_prob_up": max(0.01, min(0.99, 0.5 + (rank.expected_return_bps / 120.0))),
                    "expected_return_bps": float(rank.expected_return_bps),
                    "volatility_bps": max(1.0, float(rank.uncertainty_bps) * 0.9),
                    "drawdown_risk_bps": max(1.0, float(rank.uncertainty_bps) * 0.55),
                    "confidence": float(rank.confidence),
                    "uncertainty_bps": float(rank.uncertainty_bps),
                }
            )
        self._publish_signal_result(task=task, rows=rows)
        self._publish_audit_event(
            event_type="compute_forecast_completed",
            payload={
                "task_id": task.task_id,
                "symbol_count": len(rows),
                "ok": bool(rows),
            },
            task=task,
        )

    def _handle_optimize_task(self, task: DistributedEnvelope) -> None:
        payload = task.payload if isinstance(task.payload, dict) else {}
        targets = payload.get("bounded_parameters", [])
        if not isinstance(targets, list):
            targets = []
        proposals: list[dict[str, Any]] = []
        for item in targets:
            if not isinstance(item, Mapping):
                continue
            key = str(item.get("key", "") or "").strip()
            if not key:
                continue
            current = float(item.get("current", 0.0) or 0.0)
            step = float(item.get("step", 0.0) or 0.0)
            min_v = float(item.get("min", current) or current)
            max_v = float(item.get("max", current) or current)
            candidate = current + step
            if candidate < min_v:
                candidate = min_v
            if candidate > max_v:
                candidate = max_v
            proposals.append(
                {
                    "key": key,
                    "current": current,
                    "candidate": candidate,
                    "min": min_v,
                    "max": max_v,
                    "confidence": 0.5,
                    "bounded": True,
                }
            )
        self._publish_signal_result(
            task=task,
            rows=[
                {
                    "symbol": "*",
                    "market_class": "mixed",
                    "kind": "optimize_result",
                    "proposal_count": len(proposals),
                    "proposals": proposals,
                }
            ],
        )
        self._publish_audit_event(
            event_type="compute_optimize_completed",
            payload={
                "task_id": task.task_id,
                "proposal_count": len(proposals),
                "ok": True,
            },
            task=task,
        )

    def poll_once(self) -> dict[str, Any]:
        if not self.ready:
            return {"status": "error", "reason": "not_connected"}
        try:
            rows = self._client.xreadgroup(  # type: ignore[union-attr]
                self.groups.compute_node,
                self.config.consumer_name,
                {
                    self.streams.task_scan: ">",
                    self.streams.task_forecast: ">",
                    self.streams.task_optimize: ">",
                },
                count=32,
                block=int(self.config.block_ms),
            )
        except Exception as exc:
            if "NOGROUP" in str(exc):
                self._groups_ready = False
                self._ensure_groups()
                return {"status": "idle", "reason": "consumer_group_initialized"}
            self._last_error = str(exc)
            return {"status": "error", "reason": f"read_failed:{exc}"}
        if not rows:
            return {"status": "idle", "reason": "no_tasks"}
        processed = 0
        skipped = 0
        errored = 0
        for stream_name, msg_id, env in self._decode_rows(rows):
            if not env.task_id:
                skipped += 1
                try:
                    self._client.xack(stream_name, self.groups.compute_node, msg_id)  # type: ignore[union-attr]
                except Exception:
                    pass
                continue
            if env.idempotency_key and env.idempotency_key in self._seen_idempotency:
                skipped += 1
                try:
                    self._client.xack(stream_name, self.groups.compute_node, msg_id)  # type: ignore[union-attr]
                except Exception:
                    pass
                continue
            if env.idempotency_key:
                self._seen_idempotency.add(env.idempotency_key)
            if env.expired:
                skipped += 1
                try:
                    self._client.xack(stream_name, self.groups.compute_node, msg_id)  # type: ignore[union-attr]
                except Exception:
                    pass
                continue
            kind = str((env.payload or {}).get("kind", "") or "").strip().lower()
            try:
                if kind in {"scan_rank", "scan"}:
                    self._handle_scan_task(env)
                    processed += 1
                elif kind in {"forecast", "forecast_batch"}:
                    self._handle_forecast_task(env)
                    processed += 1
                elif kind in {"optimize", "optimize_bounds"}:
                    self._handle_optimize_task(env)
                    processed += 1
                else:
                    skipped += 1
            except Exception as exc:
                errored += 1
                self._last_error = str(exc)
                self._publish_audit_event(
                    event_type="compute_task_error",
                    payload={
                        "task_id": env.task_id,
                        "kind": kind,
                        "error": str(exc),
                    },
                    task=env,
                )
            finally:
                try:
                    self._client.xack(stream_name, self.groups.compute_node, msg_id)  # type: ignore[union-attr]
                except Exception:
                    pass
        return {"status": "ok", "processed": processed, "skipped": skipped, "errored": errored}

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
