from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import time
from typing import Any, Mapping


DEFAULT_STREAM_PREFIX = "autobot"
DEFAULT_PAYLOAD_VERSION = "v1"
DEFAULT_GROUP_LIVE_NODE = "live_node"
DEFAULT_GROUP_COMPUTE_NODE = "compute_node"


@dataclass(frozen=True)
class DistributedStreamNames:
    """Canonical stream names for the distributed runtime contract."""

    task_scan: str
    task_forecast: str
    task_optimize: str
    result_signals: str
    result_rankings: str
    audit_events: str

    @classmethod
    def from_prefix(cls, prefix: str = DEFAULT_STREAM_PREFIX) -> "DistributedStreamNames":
        root = str(prefix or DEFAULT_STREAM_PREFIX).strip() or DEFAULT_STREAM_PREFIX
        return cls(
            task_scan=f"{root}.tasks.scan",
            task_forecast=f"{root}.tasks.forecast",
            task_optimize=f"{root}.tasks.optimize",
            result_signals=f"{root}.results.signals",
            result_rankings=f"{root}.results.rankings",
            audit_events=f"{root}.events.audit",
        )


@dataclass(frozen=True)
class DistributedConsumerGroups:
    """Canonical consumer-group names for distributed Redis streams."""

    live_node: str = DEFAULT_GROUP_LIVE_NODE
    compute_node: str = DEFAULT_GROUP_COMPUTE_NODE

    @classmethod
    def from_env(
        cls,
        *,
        live_node: str | None = None,
        compute_node: str | None = None,
    ) -> "DistributedConsumerGroups":
        live = str(live_node or DEFAULT_GROUP_LIVE_NODE).strip() or DEFAULT_GROUP_LIVE_NODE
        compute = str(compute_node or DEFAULT_GROUP_COMPUTE_NODE).strip() or DEFAULT_GROUP_COMPUTE_NODE
        return cls(live_node=live, compute_node=compute)


@dataclass(frozen=True)
class DistributedEnvelope:
    """Redis-stream message envelope used by live and compute nodes."""

    task_id: str
    run_id: str
    symbol: str
    market_class: str
    ts: float
    ttl_s: float
    payload_version: str
    idempotency_key: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": str(self.task_id),
            "run_id": str(self.run_id),
            "symbol": str(self.symbol),
            "market_class": str(self.market_class),
            "ts": float(self.ts),
            "ttl_s": float(self.ttl_s),
            "payload_version": str(self.payload_version),
            "idempotency_key": str(self.idempotency_key),
            "payload": dict(self.payload),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DistributedEnvelope":
        payload = raw.get("payload", {})
        if not isinstance(payload, Mapping):
            payload = {}
        return cls(
            task_id=str(raw.get("task_id", "") or ""),
            run_id=str(raw.get("run_id", "") or ""),
            symbol=str(raw.get("symbol", "") or ""),
            market_class=str(raw.get("market_class", "") or ""),
            ts=float(raw.get("ts", 0.0) or 0.0),
            ttl_s=max(0.1, float(raw.get("ttl_s", 5.0) or 5.0)),
            payload_version=str(raw.get("payload_version", DEFAULT_PAYLOAD_VERSION) or DEFAULT_PAYLOAD_VERSION),
            idempotency_key=str(raw.get("idempotency_key", "") or ""),
            payload=dict(payload),
        )

    @property
    def expired(self) -> bool:
        return (time.time() - float(self.ts)) > float(self.ttl_s)


def build_idempotency_key(
    *,
    stream: str,
    run_id: str,
    symbol: str,
    payload: Mapping[str, Any],
    payload_version: str = DEFAULT_PAYLOAD_VERSION,
) -> str:
    """Build deterministic idempotency key for distributed writes."""
    canonical = json.dumps(
        {
            "stream": str(stream),
            "run_id": str(run_id),
            "symbol": str(symbol),
            "payload_version": str(payload_version),
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def encode_stream_entry(envelope: DistributedEnvelope) -> dict[str, str]:
    """Encode envelope to Redis stream fields."""
    return {"data": json.dumps(envelope.to_dict(), sort_keys=True, separators=(",", ":"), default=str)}


def decode_stream_entry(raw: Mapping[str, Any]) -> DistributedEnvelope:
    """Decode Redis stream fields into a typed envelope."""
    blob = raw.get("data", "{}")
    if isinstance(blob, bytes):
        text = blob.decode("utf-8", errors="ignore")
    else:
        text = str(blob)
    try:
        payload = json.loads(text)
    except Exception:
        payload = {}
    if not isinstance(payload, Mapping):
        payload = {}
    return DistributedEnvelope.from_mapping(payload)
