from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatch
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, time
from typing import Any, Callable, Iterable, Mapping

from autonomous_investment_robot.services.event_store.service import EventStore
from autonomous_investment_robot.services.reliability.bus import ReliabilityBus


EVENT_DOMAINS: tuple[str, ...] = (
    "market",
    "account",
    "execution",
    "risk",
    "regime",
    "mission",
    "strategy",
    "telemetry",
    "system",
    "research",
)


EVENT_TYPE_DOMAIN: dict[str, str] = {
    "MarketTickEvent": "market",
    "BookSnapshotEvent": "market",
    "TradePrintEvent": "market",
    "CandleEvent": "market",
    "FundingEvent": "regime",
    "OpenInterestEvent": "regime",
    "CrossVenueEvent": "regime",
    "AccountSnapshotEvent": "account",
    "OrderEvent": "execution",
    "FillEvent": "execution",
    "RiskEvent": "risk",
    "HealthEvent": "telemetry",
    "RegimeEvent": "regime",
    "StrategyProposalEvent": "strategy",
    "MissionEvent": "mission",
    "ExecutionPlanEvent": "execution",
}

CANONICAL_EVENT_TYPES: tuple[str, ...] = tuple(EVENT_TYPE_DOMAIN.keys())
LEGACY_EVENT_TYPE_MAP: dict[str, str] = {
    "MarketEvent": "MarketTickEvent",
    "OrderIntentEvent": "StrategyProposalEvent",
    "OrderEvent": "OrderEvent",
    "FillEvent": "FillEvent",
    "PositionEvent": "AccountSnapshotEvent",
    "RiskEvent": "RiskEvent",
    "ComplianceEvent": "HealthEvent",
}


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _float_ts(value: float | None = None) -> float:
    if value is None:
        return datetime.now(timezone.utc).timestamp()
    return float(value)


def _float_ts_any(value: Any) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if value in {None, ""}:
        return _float_ts(None)
    if isinstance(value, (int, float)):
        return _float_ts(float(value))
    if isinstance(value, str):
        text = str(value).strip()
        if not text:
            return _float_ts(None)
        try:
            return _float_ts(float(text))
        except Exception:
            pass
        try:
            normalized = text.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except Exception:
            return _float_ts(None)
    return _float_ts(None)


def _legacy_event_mapping(legacy_event: Any) -> dict[str, Any]:
    if isinstance(legacy_event, Mapping):
        return dict(legacy_event)
    if isinstance(legacy_event, UniverseEventEnvelope):
        return legacy_event.to_dict()
    to_dict = getattr(legacy_event, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    fields = getattr(legacy_event, "__dict__", None)
    if isinstance(fields, Mapping):
        return dict(fields)
    return {}


def adapt_legacy_event(
    legacy_event: UniverseEventEnvelope | Mapping[str, Any] | Any,
    *,
    source: str = "legacy_adapter",
    metadata: Mapping[str, Any] | None = None,
) -> UniverseEventEnvelope:
    if isinstance(legacy_event, UniverseEventEnvelope):
        return legacy_event

    raw = _legacy_event_mapping(legacy_event)
    if not raw:
        raise ValueError("legacy_event_unreadable")

    payload_raw = raw.get("payload", {})
    if isinstance(payload_raw, Mapping):
        payload = dict(payload_raw)
    else:
        payload = {}

    symbol = str(raw.get("symbol", payload.get("symbol", raw.get("partition_key", "global"))) or "global")
    venue = str(raw.get("venue", payload.get("venue", "legacy")) or "legacy")
    payload.setdefault("symbol", symbol)
    payload.setdefault("venue", venue)

    legacy_event_type = str(raw.get("event_type", "") or "")
    canonical_event_type = LEGACY_EVENT_TYPE_MAP.get(legacy_event_type, legacy_event_type)
    if not canonical_event_type:
        canonical_event_type = "HealthEvent"
    if canonical_event_type not in CANONICAL_EVENT_TYPES:
        canonical_event_type = "HealthEvent"
        payload.setdefault("status", "WARN")
        payload.setdefault("latency_ms", 0.0)
        payload.setdefault("health_score", 0.0)
        payload.setdefault("rejection_ratio", 0.0)
        payload.setdefault("stale_feed", False)
        payload.setdefault("desync", False)

    if canonical_event_type == "StrategyProposalEvent":
        payload.setdefault("strategy", str(payload.get("strategy", "legacy_intent") or "legacy_intent"))
        side = str(payload.get("side", payload.get("signal_side", "flat")) or "flat").strip().lower()
        if side not in {"buy", "sell", "flat"}:
            side = "flat"
        payload.setdefault("side", side)
        payload.setdefault("action", "trade" if side in {"buy", "sell"} else "hold")
        payload.setdefault(
            "target_notional_quote",
            max(0.0, float(payload.get("target_notional_quote", payload.get("target_notional", 0.0)) or 0.0)),
        )
        payload.setdefault("expected_value_bps", float(payload.get("expected_value_bps", 0.0) or 0.0))
        payload.setdefault("confidence", float(payload.get("confidence", 0.0) or 0.0))
    elif canonical_event_type == "HealthEvent":
        payload.setdefault("status", "OK")
        payload.setdefault("latency_ms", float(payload.get("latency_ms", 0.0) or 0.0))
        payload.setdefault("health_score", float(payload.get("health_score", 1.0) or 1.0))
        payload.setdefault("rejection_ratio", float(payload.get("rejection_ratio", 0.0) or 0.0))
        payload.setdefault("stale_feed", bool(payload.get("stale_feed", False)))
        payload.setdefault("desync", bool(payload.get("desync", False)))

    seq = int(raw.get("seq", raw.get("sequence_no", 0)) or 0)
    checksum = str(raw.get("checksum", "") or "")
    idempotency_key = str(raw.get("idempotency_key", "") or "").strip()
    if not idempotency_key:
        idempotency_key = _stable_hash(
            {
                "legacy_event_type": legacy_event_type,
                "canonical_event_type": canonical_event_type,
                "symbol": symbol,
                "venue": venue,
                "seq": seq,
                "checksum": checksum,
                "payload": payload,
            }
        )
    event_id = str(raw.get("event_id", "") or "").strip()
    if not event_id:
        event_id = _stable_hash(
            {
                "idempotency_key": idempotency_key,
                "canonical_event_type": canonical_event_type,
                "source": str(source or raw.get("source", "legacy_adapter")),
            }
        )

    meta_payload = {
        "legacy_event_type": legacy_event_type,
        "legacy_sequence": seq,
        "legacy_checksum": checksum,
        **dict(metadata or {}),
    }
    correlation = str(raw.get("correlation_id", "") or "")
    return build_event(
        event_id=event_id,
        event_type=canonical_event_type,
        source=str(source or raw.get("source", "legacy_adapter")),
        partition_key=str(raw.get("partition_key", symbol) or symbol),
        payload=payload,
        event_time=_float_ts_any(raw.get("event_time", raw.get("ts"))),
        observed_time=_float_ts_any(raw.get("observed_time", raw.get("ts"))),
        processed_time=_float_ts_any(raw.get("processed_time", raw.get("ts"))),
        correlation_id=correlation,
        sequence_no=max(0, seq),
        idempotency_key=idempotency_key,
        metadata=meta_payload,
    )


def _infer_domain(event_type: str, explicit_domain: str = "") -> str:
    domain = str(explicit_domain or "").strip().lower()
    if domain:
        if domain in EVENT_DOMAINS:
            return domain
        return "system"
    return EVENT_TYPE_DOMAIN.get(str(event_type or "").strip(), "system")


class SchemaRegistryError(ValueError):
    pass


class UnknownSchemaError(SchemaRegistryError):
    pass


class SchemaVersionError(SchemaRegistryError):
    pass


class SchemaValidationError(SchemaRegistryError):
    pass


@dataclass(frozen=True)
class EventSchemaDefinition:
    event_type: str
    event_domain: str
    schema_version: str = "v1"
    required_fields: tuple[str, ...] = field(default_factory=tuple)
    compatible_schema_versions: tuple[str, ...] = field(default_factory=tuple)
    payload_validator: Callable[[Mapping[str, Any]], None] | None = None

    def validate(self, payload: Mapping[str, Any], *, schema_version: str) -> None:
        if schema_version != self.schema_version and schema_version not in set(self.compatible_schema_versions):
            raise SchemaVersionError(
                f"schema_version_mismatch:{self.event_type}:{schema_version}!={self.schema_version}"
            )
        if not isinstance(payload, Mapping):
            raise SchemaValidationError(f"payload_not_mapping:{self.event_type}")
        missing = [name for name in self.required_fields if name not in payload]
        if missing:
            raise SchemaValidationError(f"missing_required_fields:{self.event_type}:{','.join(sorted(missing))}")
        if self.payload_validator is not None:
            self.payload_validator(payload)


class EventSchemaRegistry:
    """Typed event schema registry with version and compatibility validation."""

    def __init__(self) -> None:
        self._schemas: dict[tuple[str, str], EventSchemaDefinition] = {}
        self._latest_by_type: dict[str, str] = {}

    def register(self, definition: EventSchemaDefinition) -> None:
        key = (definition.event_type, definition.schema_version)
        self._schemas[key] = definition
        self._latest_by_type[definition.event_type] = definition.schema_version

    def resolve(self, event_type: str, schema_version: str) -> EventSchemaDefinition:
        event_name = str(event_type or "").strip()
        version = str(schema_version or "").strip() or self._latest_by_type.get(event_name, "v1")
        direct = self._schemas.get((event_name, version))
        if direct is not None:
            return direct
        latest_version = self._latest_by_type.get(event_name)
        if latest_version is None:
            raise UnknownSchemaError(f"unknown_event_type:{event_name}")
        latest = self._schemas.get((event_name, latest_version))
        if latest is None:
            raise UnknownSchemaError(f"missing_schema_definition:{event_name}")
        if version in set(latest.compatible_schema_versions):
            return latest
        raise SchemaVersionError(f"unknown_schema_version:{event_name}:{version}")

    def validate(
        self,
        *,
        event_type: str,
        event_domain: str,
        schema_version: str,
        payload: Mapping[str, Any],
    ) -> EventSchemaDefinition:
        definition = self.resolve(event_type, schema_version)
        if str(event_domain or "").strip() and definition.event_domain != str(event_domain):
            raise SchemaValidationError(
                f"event_domain_mismatch:{event_type}:{event_domain}!={definition.event_domain}"
            )
        definition.validate(payload, schema_version=schema_version)
        return definition


def _make_default_schema_registry() -> EventSchemaRegistry:
    registry = EventSchemaRegistry()
    definitions = (
        EventSchemaDefinition("MarketTickEvent", "market", "v1", ("symbol", "venue")),
        EventSchemaDefinition("BookSnapshotEvent", "market", "v1", ("symbol", "venue")),
        EventSchemaDefinition("TradePrintEvent", "market", "v1", ("symbol", "venue")),
        EventSchemaDefinition("CandleEvent", "market", "v1", ("symbol", "venue")),
        EventSchemaDefinition("FundingEvent", "regime", "v1", ("venue",)),
        EventSchemaDefinition("OpenInterestEvent", "regime", "v1", ("venue",)),
        EventSchemaDefinition("CrossVenueEvent", "regime", "v1", ("venue",)),
        EventSchemaDefinition("AccountSnapshotEvent", "account", "v1", ("symbol", "venue")),
        EventSchemaDefinition("OrderEvent", "execution", "v1", ("symbol", "venue")),
        EventSchemaDefinition("FillEvent", "execution", "v1", ("symbol", "venue")),
        EventSchemaDefinition("RiskEvent", "risk", "v1", ("symbol", "venue")),
        EventSchemaDefinition("HealthEvent", "telemetry", "v1", ("symbol", "venue")),
        EventSchemaDefinition("RegimeEvent", "regime", "v1", ("symbol", "venue")),
        EventSchemaDefinition("StrategyProposalEvent", "strategy", "v1", ("symbol", "venue", "strategy")),
        EventSchemaDefinition("MissionEvent", "mission", "v1", ("symbol", "venue", "mission")),
        EventSchemaDefinition("ExecutionPlanEvent", "execution", "v1", ("symbol", "venue", "strategy")),
    )
    for definition in definitions:
        registry.register(definition)
    return registry


@dataclass
class EventFabricMetrics:
    published_total: int = 0
    rejected_total: int = 0
    schema_reject_total: int = 0
    dead_letter_total: int = 0
    handler_calls: int = 0
    handler_failures: int = 0
    handler_latency_ms_total: float = 0.0
    queue_depth: int = 0
    replay_event_count: int = 0
    replay_elapsed_s: float = 0.0
    warning_mode: bool = False
    started_at_s: float = field(default_factory=time)

    def to_dict(self) -> dict[str, Any]:
        elapsed = max(1e-9, time() - self.started_at_s)
        handler_latency_avg = (
            self.handler_latency_ms_total / max(self.handler_calls, 1)
            if self.handler_calls > 0
            else 0.0
        )
        publish_denom = max(self.published_total + self.rejected_total, 1)
        replay_speed = (
            self.replay_event_count / max(self.replay_elapsed_s, 1e-9)
            if self.replay_event_count > 0
            else 0.0
        )
        return {
            "published_total": self.published_total,
            "rejected_total": self.rejected_total,
            "schema_reject_total": self.schema_reject_total,
            "dead_letter_total": self.dead_letter_total,
            "handler_calls": self.handler_calls,
            "handler_failures": self.handler_failures,
            "handler_latency_ms_avg": handler_latency_avg,
            "queue_depth": self.queue_depth,
            "event_throughput_eps": self.published_total / elapsed,
            "dead_letter_rate": self.dead_letter_total / publish_denom,
            "schema_reject_rate": self.schema_reject_total / publish_denom,
            "replay_event_count": self.replay_event_count,
            "replay_elapsed_s": self.replay_elapsed_s,
            "replay_speed_eps": replay_speed,
            "warning_mode": bool(self.warning_mode),
        }


@dataclass
class ProjectionSeed:
    market: dict[str, dict[str, Any]] = field(default_factory=dict)
    account: dict[str, dict[str, Any]] = field(default_factory=dict)
    risk: dict[str, dict[str, Any]] = field(default_factory=dict)
    health: dict[str, dict[str, Any]] = field(default_factory=dict)

    def apply(self, event: "UniverseEventEnvelope") -> None:
        key = str(event.partition_key or event.subject or "global")
        record = {
            "event_time": float(event.event_time),
            "event_type": event.event_type,
            "source": event.source,
            "payload": dict(event.payload),
        }
        if event.event_domain == "market":
            self.market[key] = record
        elif event.event_domain == "account":
            self.account[key] = record
        elif event.event_domain == "risk":
            self.risk[key] = record
        elif event.event_domain == "telemetry":
            self.health[key] = record

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": dict(self.market),
            "account": dict(self.account),
            "risk": dict(self.risk),
            "health": dict(self.health),
        }


@dataclass(frozen=True)
class UniverseEventEnvelope:
    event_id: str
    event_type: str
    event_domain: str
    schema_version: str
    source: str
    subject: str
    partition_key: str
    event_time: float
    observed_time: float
    processed_time: float
    correlation_id: str = ""
    causation_id: str = ""
    sequence_no: int = 0
    priority: int = 5
    is_replay: bool = False
    is_snapshot: bool = False
    is_synthetic: bool = False
    producer: str = ""
    trace_id: str = ""
    tags: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> str:
        # Backward-compatible alias.
        return self.schema_version

    @property
    def ts(self) -> float:
        # Backward-compatible alias.
        return self.event_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": str(self.event_type),
            "event_domain": str(self.event_domain),
            "schema_version": str(self.schema_version),
            "source": str(self.source),
            "subject": str(self.subject),
            "partition_key": str(self.partition_key),
            "event_time": float(self.event_time),
            "observed_time": float(self.observed_time),
            "processed_time": float(self.processed_time),
            "correlation_id": str(self.correlation_id),
            "causation_id": str(self.causation_id),
            "sequence_no": int(self.sequence_no),
            "priority": int(self.priority),
            "is_replay": bool(self.is_replay),
            "is_snapshot": bool(self.is_snapshot),
            "is_synthetic": bool(self.is_synthetic),
            "producer": str(self.producer),
            "trace_id": str(self.trace_id),
            "tags": dict(self.tags),
            "payload": dict(self.payload),
            "idempotency_key": str(self.idempotency_key),
            "metadata": dict(self.metadata),
            # Legacy aliases:
            "version": str(self.schema_version),
            "ts": float(self.event_time),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "UniverseEventEnvelope":
        payload = raw.get("payload", {})
        metadata = raw.get("metadata", {})
        tags_raw = raw.get("tags", {})
        if not isinstance(payload, Mapping):
            payload = {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        if isinstance(tags_raw, Mapping):
            tags = {str(k): str(v) for k, v in tags_raw.items()}
        elif isinstance(tags_raw, list):
            tags = {str(item): "1" for item in tags_raw}
        else:
            tags = {}
        event_type = str(raw.get("event_type", "") or "")
        schema_version = str(raw.get("schema_version", raw.get("version", "v1")) or "v1")
        event_time = _float_ts(float(raw.get("event_time", raw.get("ts", 0.0)) or 0.0))
        observed_time = _float_ts(float(raw.get("observed_time", event_time) or event_time))
        processed_time = _float_ts(float(raw.get("processed_time", observed_time) or observed_time))
        return cls(
            event_id=str(raw.get("event_id", "") or ""),
            event_type=event_type,
            event_domain=_infer_domain(event_type, str(raw.get("event_domain", "") or "")),
            schema_version=schema_version,
            source=str(raw.get("source", "") or ""),
            subject=str(raw.get("subject", raw.get("partition_key", "")) or ""),
            partition_key=str(raw.get("partition_key", "") or ""),
            event_time=event_time,
            observed_time=observed_time,
            processed_time=processed_time,
            correlation_id=str(raw.get("correlation_id", "") or ""),
            causation_id=str(raw.get("causation_id", "") or ""),
            sequence_no=int(raw.get("sequence_no", 0) or 0),
            priority=int(raw.get("priority", 5) or 5),
            is_replay=bool(raw.get("is_replay", False)),
            is_snapshot=bool(raw.get("is_snapshot", False)),
            is_synthetic=bool(raw.get("is_synthetic", False)),
            producer=str(raw.get("producer", raw.get("source", "")) or ""),
            trace_id=str(raw.get("trace_id", raw.get("correlation_id", "")) or ""),
            tags=tags,
            payload=dict(payload),
            idempotency_key=str(raw.get("idempotency_key", raw.get("event_id", "")) or ""),
            metadata=dict(metadata),
        )


def build_event(
    *,
    event_type: str,
    source: str,
    partition_key: str,
    payload: Mapping[str, Any],
    ts: float | None = None,
    event_domain: str = "",
    subject: str = "",
    event_time: float | None = None,
    observed_time: float | None = None,
    processed_time: float | None = None,
    version: str = "v1",
    schema_version: str | None = None,
    event_id: str | None = None,
    idempotency_key: str | None = None,
    correlation_id: str = "",
    causation_id: str = "",
    sequence_no: int = 0,
    priority: int = 5,
    is_replay: bool = False,
    is_snapshot: bool = False,
    is_synthetic: bool = False,
    producer: str = "",
    trace_id: str = "",
    tags: Mapping[str, str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> UniverseEventEnvelope:
    ts_value = _float_ts(event_time if event_time is not None else ts)
    observed_value = _float_ts(observed_time if observed_time is not None else ts_value)
    processed_value = _float_ts(processed_time if processed_time is not None else observed_value)
    event_payload = dict(payload)
    meta = dict(metadata or {})
    normalized_type = str(event_type or "").strip() or "UnknownEvent"
    normalized_source = str(source or "").strip() or "unknown"
    normalized_partition = str(partition_key or "").strip() or "global"
    normalized_subject = str(subject or normalized_partition).strip() or normalized_partition
    normalized_domain = _infer_domain(normalized_type, event_domain)
    schema = str(schema_version or version or "v1")
    normalized_tags = {str(k): str(v) for k, v in dict(tags or {}).items()}
    generated_event_id = event_id or _stable_hash(
        {
            "event_type": normalized_type,
            "event_domain": normalized_domain,
            "source": normalized_source,
            "partition_key": normalized_partition,
            "subject": normalized_subject,
            "event_time": round(ts_value, 6),
            "payload": event_payload,
            "metadata": meta,
        }
    )
    generated_idempotency = idempotency_key or generated_event_id
    return UniverseEventEnvelope(
        event_id=str(generated_event_id),
        event_type=normalized_type,
        event_domain=normalized_domain,
        schema_version=schema,
        source=normalized_source,
        subject=normalized_subject,
        partition_key=normalized_partition,
        event_time=ts_value,
        observed_time=observed_value,
        processed_time=processed_value,
        correlation_id=str(correlation_id or ""),
        causation_id=str(causation_id or ""),
        sequence_no=max(0, int(sequence_no or 0)),
        priority=max(0, int(priority or 0)),
        is_replay=bool(is_replay),
        is_snapshot=bool(is_snapshot),
        is_synthetic=bool(is_synthetic),
        producer=str(producer or normalized_source),
        trace_id=str(trace_id or correlation_id or ""),
        tags=normalized_tags,
        payload=event_payload,
        idempotency_key=str(generated_idempotency),
        metadata=meta,
    )


class EventFabric:
    """Canonical publish/replay surface for UNIVERSE CORE events."""

    def __init__(
        self,
        run_dir: str,
        *,
        bus: ReliabilityBus | None = None,
        store: EventStore | None = None,
        version: str = "v1",
        middlewares: Iterable[Callable[[UniverseEventEnvelope], UniverseEventEnvelope]] | None = None,
        schema_registry: EventSchemaRegistry | None = None,
        metrics_hooks: Iterable[Callable[[dict[str, Any]], None]] | None = None,
        dedup_ttl_s: float = 300.0,
        max_dedup_entries: int = 20_000,
        enable_schema_validation: bool = True,
        enable_subscriber_dispatch: bool = True,
    ) -> None:
        self.run_dir = str(run_dir)
        self.version = str(version or "v1")
        self.bus = bus or ReliabilityBus(self.run_dir)
        self.store = store or EventStore(self.run_dir)
        self.middlewares = list(middlewares or [])
        self.schema_registry = schema_registry or _make_default_schema_registry()
        self.metrics_hooks = list(metrics_hooks or [])
        self.enable_schema_validation = bool(enable_schema_validation)
        self.enable_subscriber_dispatch = bool(enable_subscriber_dispatch)
        self.dedup_ttl_s = max(1.0, float(dedup_ttl_s))
        self.max_dedup_entries = max(100, int(max_dedup_entries))
        self.metrics = EventFabricMetrics()
        self.projections = ProjectionSeed()
        self._dedup_cache: dict[str, float] = {}
        self._subscribers: dict[int, tuple[str, Callable[[UniverseEventEnvelope], None]]] = {}
        self._subscriber_id = 0
        self._sequence_no = 0
        self.dead_letter_path = Path(self.run_dir) / "universe_event_dead_letter.jsonl"

    def subscribe(self, pattern: str, handler: Callable[[UniverseEventEnvelope], None]) -> int:
        self._subscriber_id += 1
        token = self._subscriber_id
        self._subscribers[token] = (str(pattern or "*"), handler)
        return token

    def unsubscribe(self, token: int) -> None:
        self._subscribers.pop(int(token), None)

    def publish(self, event: UniverseEventEnvelope) -> UniverseEventEnvelope | None:
        try:
            current = self._apply_middlewares(event)
        except Exception as exc:
            self.metrics.rejected_total += 1
            self._set_warning_mode(f"middleware_failure:{exc}")
            self._record_dead_letter(None, reason="middleware_failure", error=str(exc))
            self._emit_metrics_hook(kind="reject", reason="middleware_failure")
            return None

        normalized = self._normalize_envelope(current)
        if self._is_duplicate(normalized):
            self._emit_metrics_hook(kind="duplicate", event=normalized)
            self._observe_queue_depth()
            return None
        if not self._validate_schema(normalized):
            self._emit_metrics_hook(kind="reject", reason="schema_validation", event=normalized)
            self._observe_queue_depth()
            return None

        bus_persisted = False
        store_persisted = False
        try:
            published = self.bus.publish(
                "universe",
                normalized.to_dict(),
                event_id=normalized.event_id,
                idempotency_key=normalized.idempotency_key,
            )
            if published is None:
                self._observe_queue_depth()
                return None
            bus_persisted = True
        except Exception as exc:
            self._set_warning_mode(f"bus_publish_failure:{exc}")
            self._record_dead_letter(normalized, reason="bus_publish_failure", error=str(exc))

        try:
            self.store.append("universe", normalized.to_dict())
            store_persisted = True
        except Exception as exc:
            self._set_warning_mode(f"store_append_failure:{exc}")
            self._record_dead_letter(normalized, reason="store_append_failure", error=str(exc))

        if not (bus_persisted or store_persisted):
            self.metrics.rejected_total += 1
            self._emit_metrics_hook(kind="reject", reason="persistence_failure", event=normalized)
            self._observe_queue_depth()
            return None

        self.projections.apply(normalized)
        self.metrics.published_total += 1
        self._dispatch_handlers(normalized)
        self._observe_queue_depth()
        self._emit_metrics_hook(kind="publish", event=normalized)
        return normalized

    def emit(
        self,
        *,
        event_type: str,
        source: str,
        partition_key: str,
        payload: Mapping[str, Any],
        ts: float | None = None,
        event_domain: str = "",
        subject: str = "",
        event_time: float | None = None,
        observed_time: float | None = None,
        processed_time: float | None = None,
        schema_version: str | None = None,
        event_id: str | None = None,
        idempotency_key: str | None = None,
        correlation_id: str = "",
        causation_id: str = "",
        sequence_no: int = 0,
        priority: int = 5,
        is_replay: bool = False,
        is_snapshot: bool = False,
        is_synthetic: bool = False,
        producer: str = "",
        trace_id: str = "",
        tags: Mapping[str, str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> UniverseEventEnvelope | None:
        event = build_event(
            event_type=event_type,
            source=source,
            partition_key=partition_key,
            payload=payload,
            ts=ts,
            event_domain=event_domain,
            subject=subject,
            event_time=event_time,
            observed_time=observed_time,
            processed_time=processed_time,
            schema_version=schema_version or self.version,
            version=self.version,
            event_id=event_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            causation_id=causation_id,
            sequence_no=sequence_no,
            priority=priority,
            is_replay=is_replay,
            is_snapshot=is_snapshot,
            is_synthetic=is_synthetic,
            producer=producer,
            trace_id=trace_id,
            tags=tags,
            metadata=metadata,
        )
        return self.publish(event)

    def ingest_legacy_event(
        self,
        legacy_event: UniverseEventEnvelope | Mapping[str, Any] | Any,
        *,
        source: str = "legacy_adapter",
        metadata: Mapping[str, Any] | None = None,
    ) -> UniverseEventEnvelope | None:
        try:
            adapted = adapt_legacy_event(
                legacy_event,
                source=source,
                metadata=metadata,
            )
        except Exception as exc:
            self.metrics.rejected_total += 1
            self._record_dead_letter(None, reason="legacy_adapter_reject", error=str(exc))
            self._emit_metrics_hook(kind="reject", reason="legacy_adapter_reject")
            self._observe_queue_depth()
            return None
        return self.publish(adapted)

    def ingest_legacy_events(
        self,
        legacy_events: Iterable[UniverseEventEnvelope | Mapping[str, Any] | Any],
        *,
        source: str = "legacy_adapter",
        metadata: Mapping[str, Any] | None = None,
    ) -> list[UniverseEventEnvelope]:
        published: list[UniverseEventEnvelope] = []
        for row in legacy_events:
            event = self.ingest_legacy_event(row, source=source, metadata=metadata)
            if event is not None:
                published.append(event)
        return published

    def replay(
        self,
        *,
        event_type: str = "",
        event_domain: str = "",
        correlation_id: str = "",
        partition_key: str = "",
        limit: int = 0,
    ) -> list[UniverseEventEnvelope]:
        started = perf_counter()
        rows = self.store.load("universe")
        if not rows:
            rows = [row.payload for row in self.bus.replay("universe")]
        events = [UniverseEventEnvelope.from_mapping(row) for row in rows if isinstance(row, Mapping)]
        events.sort(key=lambda row: (row.event_time, row.sequence_no, row.event_id))
        if event_type:
            events = [row for row in events if row.event_type == event_type]
        if event_domain:
            expected_domain = str(event_domain).strip().lower()
            events = [row for row in events if row.event_domain == expected_domain]
        if correlation_id:
            cid = str(correlation_id)
            events = [row for row in events if row.correlation_id == cid]
        if partition_key:
            part = str(partition_key)
            events = [row for row in events if row.partition_key == part]
        if limit > 0:
            events = events[-int(limit) :]
        elapsed = max(perf_counter() - started, 1e-9)
        self.metrics.replay_event_count = len(events)
        self.metrics.replay_elapsed_s = elapsed
        self._emit_metrics_hook(kind="replay", count=len(events), elapsed_s=elapsed)
        return events

    def query(
        self,
        *,
        event_type: str = "",
        event_domain: str = "",
        correlation_id: str = "",
        partition_key: str = "",
        limit: int = 0,
    ) -> list[UniverseEventEnvelope]:
        return self.replay(
            event_type=event_type,
            event_domain=event_domain,
            correlation_id=correlation_id,
            partition_key=partition_key,
            limit=limit,
        )

    def trace_correlation(self, correlation_id: str) -> list[UniverseEventEnvelope]:
        return self.query(correlation_id=correlation_id)

    def metrics_snapshot(self) -> dict[str, Any]:
        self._observe_queue_depth()
        return self.metrics.to_dict()

    def projection_snapshot(self) -> dict[str, Any]:
        return self.projections.to_dict()

    def _apply_middlewares(self, event: UniverseEventEnvelope) -> UniverseEventEnvelope:
        current = event
        for middleware in self.middlewares:
            current = middleware(current)
        return current

    def _normalize_envelope(self, event: UniverseEventEnvelope) -> UniverseEventEnvelope:
        self._sequence_no = max(self._sequence_no, int(event.sequence_no)) + 1
        processed = _float_ts()
        if event.idempotency_key:
            idempotency_key = event.idempotency_key
        else:
            idempotency_key = f"{event.source}:{event.event_id}"
        return build_event(
            event_id=event.event_id,
            event_type=event.event_type,
            event_domain=event.event_domain,
            schema_version=event.schema_version,
            source=event.source,
            subject=event.subject,
            partition_key=event.partition_key,
            payload=event.payload,
            event_time=event.event_time,
            observed_time=event.observed_time,
            processed_time=processed,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            sequence_no=max(int(event.sequence_no), self._sequence_no),
            priority=event.priority,
            is_replay=event.is_replay,
            is_snapshot=event.is_snapshot,
            is_synthetic=event.is_synthetic,
            producer=event.producer or event.source,
            trace_id=event.trace_id or event.correlation_id,
            tags=event.tags,
            idempotency_key=idempotency_key,
            metadata=event.metadata,
            version=self.version,
        )

    def _validate_schema(self, event: UniverseEventEnvelope) -> bool:
        if not self.enable_schema_validation:
            return True
        try:
            self.schema_registry.validate(
                event_type=event.event_type,
                event_domain=event.event_domain,
                schema_version=event.schema_version,
                payload=event.payload,
            )
            return True
        except SchemaRegistryError as exc:
            self.metrics.rejected_total += 1
            self.metrics.schema_reject_total += 1
            self._record_dead_letter(event, reason="schema_reject", error=str(exc))
            return False

    def _is_duplicate(self, event: UniverseEventEnvelope) -> bool:
        now_ts = _float_ts()
        key = f"{event.source}:{event.idempotency_key or event.event_id}"
        self._prune_dedup_cache(now_ts)
        expires = self._dedup_cache.get(key)
        if expires is not None and expires > now_ts:
            return True
        self._dedup_cache[key] = now_ts + self.dedup_ttl_s
        if len(self._dedup_cache) > self.max_dedup_entries:
            # Remove the oldest expiring keys first to keep bounded memory.
            for stale_key, _ in sorted(self._dedup_cache.items(), key=lambda item: item[1])[
                : len(self._dedup_cache) - self.max_dedup_entries
            ]:
                self._dedup_cache.pop(stale_key, None)
        return False

    def _prune_dedup_cache(self, now_ts: float) -> None:
        stale_keys = [key for key, expiry in self._dedup_cache.items() if expiry <= now_ts]
        for key in stale_keys:
            self._dedup_cache.pop(key, None)

    def _dispatch_handlers(self, event: UniverseEventEnvelope) -> None:
        if not self.enable_subscriber_dispatch or not self._subscribers:
            return
        for token, (pattern, handler) in list(self._subscribers.items()):
            if not self._pattern_matches(pattern, event):
                continue
            start = perf_counter()
            try:
                handler(event)
            except Exception as exc:
                self.metrics.handler_failures += 1
                self._record_dead_letter(
                    event,
                    reason="handler_failure",
                    error=f"subscriber={token}:{pattern}:{exc}",
                )
            finally:
                elapsed_ms = max(0.0, (perf_counter() - start) * 1000.0)
                self.metrics.handler_calls += 1
                self.metrics.handler_latency_ms_total += elapsed_ms

    def _pattern_matches(self, pattern: str, event: UniverseEventEnvelope) -> bool:
        token = str(pattern or "*").strip()
        if token in {"*", "**"}:
            return True
        if fnmatch(event.event_type, token):
            return True
        return fnmatch(f"{event.event_domain}.{event.event_type}", token)

    def _record_dead_letter(
        self,
        event: UniverseEventEnvelope | None,
        *,
        reason: str,
        error: str = "",
    ) -> None:
        self.metrics.dead_letter_total += 1
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "reason": str(reason),
            "error": str(error),
            "event": event.to_dict() if event is not None else {},
        }
        try:
            self.dead_letter_path.parent.mkdir(parents=True, exist_ok=True)
            with self.dead_letter_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
        except Exception:
            self._set_warning_mode("dead_letter_write_failure")

    def _set_warning_mode(self, reason: str) -> None:
        self.metrics.warning_mode = True
        self._emit_metrics_hook(kind="warning_mode", reason=reason)

    def _observe_queue_depth(self) -> None:
        events = getattr(self.bus, "_events", [])
        acked = getattr(self.bus, "_acked_ids", set())
        if isinstance(events, list):
            self.metrics.queue_depth = max(0, len(events) - len(acked if isinstance(acked, set) else []))

    def _emit_metrics_hook(self, *, kind: str, **payload: Any) -> None:
        if not self.metrics_hooks:
            return
        row = {"kind": kind, "metrics": self.metrics.to_dict(), **payload}
        for hook in self.metrics_hooks:
            try:
                hook(row)
            except Exception:
                continue
