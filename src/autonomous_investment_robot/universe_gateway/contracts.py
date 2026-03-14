from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


UniverseMode = Literal["Readonly", "Paper", "Canary", "Live"]
UniverseRole = Literal["operator", "analyst", "observer", "admin"]

DEFAULT_SCHEMA_VERSION = "v1"
EVENT_STREAM_PREFIX = "autobot.events"

EVENT_STREAMS: dict[str, str] = {
    "decision": f"{EVENT_STREAM_PREFIX}.decision",
    "execution": f"{EVENT_STREAM_PREFIX}.execution",
    "risk": f"{EVENT_STREAM_PREFIX}.risk",
    "capital": f"{EVENT_STREAM_PREFIX}.capital",
    "telemetry": f"{EVENT_STREAM_PREFIX}.telemetry",
    "simulation": f"{EVENT_STREAM_PREFIX}.simulation",
    "audit": f"{EVENT_STREAM_PREFIX}.audit",
}

WS_CHANNELS = {
    "capital",
    "decisions",
    "execution",
    "risk",
    "telemetry",
    "simulation",
}

WS_REDIS_CHANNELS: dict[str, str] = {name: f"autobot.ws.{name}" for name in WS_CHANNELS}


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    event_type: str
    timestamp: str
    run_id: str
    symbol: str
    mode: UniverseMode
    confidence: float
    source_module: str
    payload: dict[str, Any]
    schema_version: str = DEFAULT_SCHEMA_VERSION

    @classmethod
    def build(
        cls,
        *,
        event_type: str,
        run_id: str,
        symbol: str,
        mode: UniverseMode,
        confidence: float,
        source_module: str,
        payload: dict[str, Any] | None,
        event_id: str | None = None,
        timestamp: str | None = None,
        schema_version: str = DEFAULT_SCHEMA_VERSION,
    ) -> "EventEnvelope":
        return cls(
            event_id=str(event_id or uuid4()),
            event_type=str(event_type),
            timestamp=str(timestamp or datetime.now(timezone.utc).isoformat()),
            run_id=str(run_id),
            symbol=str(symbol),
            mode=mode,
            confidence=max(0.0, min(1.0, float(confidence))),
            source_module=str(source_module),
            payload=dict(payload or {}),
            schema_version=str(schema_version or DEFAULT_SCHEMA_VERSION),
        )

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "EventEnvelope":
        mode_raw = str(raw.get("mode", "Paper") or "Paper").strip()
        mode_lookup = {
            "readonly": "Readonly",
            "paper": "Paper",
            "canary": "Canary",
            "live": "Live",
        }
        mode_norm = mode_lookup.get(mode_raw.lower(), "Paper")
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        return cls(
            event_id=str(raw.get("event_id", "") or str(uuid4())),
            event_type=str(raw.get("event_type", "") or "unknown"),
            timestamp=str(raw.get("timestamp", datetime.now(timezone.utc).isoformat())),
            run_id=str(raw.get("run_id", "unknown") or "unknown"),
            symbol=str(raw.get("symbol", "") or ""),
            mode=mode_norm,  # type: ignore[assignment]
            confidence=max(0.0, min(1.0, float(raw.get("confidence", 0.0) or 0.0))),
            source_module=str(raw.get("source_module", "unknown") or "unknown"),
            payload=payload,
            schema_version=str(raw.get("schema_version", DEFAULT_SCHEMA_VERSION) or DEFAULT_SCHEMA_VERSION),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "symbol": self.symbol,
            "mode": self.mode,
            "confidence": self.confidence,
            "source_module": self.source_module,
            "payload": dict(self.payload),
            "schema_version": self.schema_version,
        }


class SystemStatusResponse(BaseModel):
    mode: str
    version: str
    uptime: float
    last_audit: str
    health: str


class CapitalStateResponse(BaseModel):
    equity: float
    drawdown_pct: float
    profit: float
    allocation: float
    survivability_score: float


class BrainModuleRow(BaseModel):
    module_name: str
    status: str
    confidence: float
    influence: float
    last_update: str


class StrategyRow(BaseModel):
    strategy_id: str
    confidence: float
    vote_weight: float
    allocation_share: float
    status: str


class ExecutionStatsResponse(BaseModel):
    blocked_orders: int
    submitted_orders: int
    filled_orders: int
    rejected_orders: int
    latency: float
    slippage: float


class TelemetryEventRow(BaseModel):
    event_type: str
    frequency: float
    reason: str
    timestamp: str


class AuditRuntimeResponse(BaseModel):
    system_state: str
    hard_invariants_status: str
    drift_status: str
    gate_status: str
    readiness_stage: str


class SimulationScenarioRow(BaseModel):
    branch_probability: float
    expected_pnl: float
    risk_score: float


class LiveStreamEnvelopeModel(BaseModel):
    type: str
    strategy: str | None = None
    confidence: float | None = None
    action: str | None = None
    symbol: str | None = None
    timestamp: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
