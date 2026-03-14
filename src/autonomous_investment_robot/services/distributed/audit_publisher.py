from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from typing import Any, Mapping

from autonomous_investment_robot.services.distributed.contracts import (
    DEFAULT_PAYLOAD_VERSION,
    DistributedEnvelope,
    DistributedStreamNames,
    build_idempotency_key,
    encode_stream_entry,
)
from autonomous_investment_robot.universe_gateway.contracts import EVENT_STREAMS, EventEnvelope


@dataclass(frozen=True)
class RedisAuditPublisherHealth:
    enabled: bool
    ok: bool
    reason: str
    backend: str
    stream: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "ok": bool(self.ok),
            "reason": str(self.reason),
            "backend": str(self.backend),
            "stream": str(self.stream),
        }


class RedisAuditPublisher:
    """Best-effort audit publisher for distributed runtime events."""

    def __init__(
        self,
        *,
        run_id: str,
        redis_url: str,
        stream_prefix: str = "autobot",
        payload_version: str = DEFAULT_PAYLOAD_VERSION,
        enabled: bool = False,
        maxlen: int = 10000,
    ) -> None:
        self.run_id = str(run_id or "").strip()
        self.redis_url = str(redis_url or "").strip()
        self.streams = DistributedStreamNames.from_prefix(stream_prefix)
        self.payload_version = str(payload_version or DEFAULT_PAYLOAD_VERSION)
        self.maxlen = max(100, int(maxlen))
        self.enabled = bool(enabled and self.redis_url and self.run_id)
        self._client = None
        self._error = ""

    @classmethod
    def from_env(cls, *, run_id: str) -> "RedisAuditPublisher":
        redis_url = str(
            os.getenv("AUTONOMOUS_REDIS_URL", "")
            or os.getenv("REDIS_URL", "")
            or ""
        ).strip()
        stream_prefix = str(os.getenv("AUTONOMOUS_STREAM_PREFIX", "autobot") or "autobot").strip()
        payload_version = str(
            os.getenv("AUTONOMOUS_STREAM_PAYLOAD_VERSION", DEFAULT_PAYLOAD_VERSION)
            or DEFAULT_PAYLOAD_VERSION
        ).strip()
        enabled = str(os.getenv("AUTONOMOUS_DISTRIBUTED_ENABLED", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        maxlen = max(100, int(float(os.getenv("AUTONOMOUS_AUDIT_STREAM_MAXLEN", "10000") or "10000")))
        return cls(
            run_id=run_id,
            redis_url=redis_url,
            stream_prefix=stream_prefix,
            payload_version=payload_version,
            enabled=enabled,
            maxlen=maxlen,
        )

    def _connect(self) -> Any:
        if not self.enabled:
            self._error = "disabled"
            return None
        if self._client is not None:
            return self._client
        try:
            import redis  # type: ignore
        except Exception as exc:
            self._error = f"dependency_missing:redis:{exc}"
            return None
        try:
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=False)
            self._client.ping()
            self._error = ""
            return self._client
        except Exception as exc:
            self._client = None
            self._error = str(exc)
            return None

    def health(self) -> RedisAuditPublisherHealth:
        client = self._connect()
        return RedisAuditPublisherHealth(
            enabled=bool(self.enabled),
            ok=bool(client is not None),
            reason="ok" if client is not None else (self._error or "unavailable"),
            backend="redis_streams",
            stream=self.streams.audit_events,
        )

    def publish(
        self,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        symbol: str = "",
        market_class: str = "",
    ) -> bool:
        client = self._connect()
        if client is None:
            return False
        now_ts = time.time()
        safe_payload: dict[str, Any] = {
            "kind": "audit_event",
            "event_type": str(event_type),
            "payload": dict(payload),
        }
        idem = build_idempotency_key(
            stream=self.streams.audit_events,
            run_id=self.run_id,
            symbol=str(symbol or "*"),
            payload=safe_payload,
            payload_version=self.payload_version,
        )
        envelope = DistributedEnvelope(
            task_id=f"audit:{int(now_ts * 1000)}",
            run_id=self.run_id,
            symbol=str(symbol or ""),
            market_class=str(market_class or ""),
            ts=now_ts,
            ttl_s=300.0,
            payload_version=self.payload_version,
            idempotency_key=idem,
            payload=safe_payload,
        )
        try:
            client.xadd(
                self.streams.audit_events,
                encode_stream_entry(envelope),
                maxlen=int(self.maxlen),
                approximate=True,
            )
            # Mirror normalized audit events into Universe contract stream.
            try:
                universe_envelope = EventEnvelope.build(
                    event_type=str(event_type),
                    run_id=self.run_id,
                    symbol=str(symbol or ""),
                    mode="Live",
                    confidence=float(payload.get("confidence", 0.0) or 0.0),
                    source_module=str(payload.get("source_module", "audit_publisher") or "audit_publisher"),
                    payload=dict(payload),
                )
                client.xadd(
                    EVENT_STREAMS["audit"],
                    {"data": json.dumps(universe_envelope.to_dict(), sort_keys=True, separators=(",", ":"), default=str)},
                    maxlen=int(self.maxlen),
                    approximate=True,
                )
            except Exception:
                pass
            return True
        except Exception as exc:
            self._error = str(exc)
            return False
