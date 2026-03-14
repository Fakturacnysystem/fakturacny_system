from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from typing import Any

from autonomous_investment_robot.universe_gateway.contracts import EVENT_STREAMS, EventEnvelope
from autonomous_investment_robot.universe_gateway.event_bus import UniverseEventBus
from autonomous_investment_robot.universe_gateway.projections import UniverseProjectionStore

LOGGER = logging.getLogger(__name__)


STREAM_TO_DOMAIN = {value: key for key, value in EVENT_STREAMS.items()}
DOMAIN_TO_WS = {
    "capital": "capital",
    "decision": "decisions",
    "execution": "execution",
    "risk": "risk",
    "telemetry": "telemetry",
    "simulation": "simulation",
    "audit": "telemetry",
}


class RealtimeProjectionWorker:
    def __init__(
        self,
        *,
        bus: UniverseEventBus,
        store: UniverseProjectionStore,
        consumer_group: str = "universe_realtime",
        consumer_name: str = "realtime-worker",
        telemetry_flush_s: float = 0.2,
    ) -> None:
        self.bus = bus
        self.store = store
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.telemetry_flush_s = max(0.05, float(telemetry_flush_s))
        self._stop = threading.Event()
        self._telemetry_buffer: list[dict[str, Any]] = []
        self._last_telemetry_flush = 0.0

    def stop(self) -> None:
        self._stop.set()

    def _build_projection_payload(self, *, domain: str, envelope: EventEnvelope) -> dict[str, Any]:
        payload = {
            "event_id": envelope.event_id,
            "event_type": envelope.event_type,
            "timestamp": envelope.timestamp,
            "run_id": envelope.run_id,
            "symbol": envelope.symbol,
            "mode": envelope.mode,
            "confidence": envelope.confidence,
            "source_module": envelope.source_module,
            "schema_version": envelope.schema_version,
            "payload": envelope.payload,
        }
        if domain == "decision":
            payload.setdefault("strategy", envelope.payload.get("strategy", ""))
            payload.setdefault("action", envelope.payload.get("action", "hold"))
            payload.setdefault("reason", envelope.payload.get("reason", ""))
            payload.setdefault("modules", envelope.payload.get("modules", []))
            payload.setdefault("strategies", envelope.payload.get("strategies", []))
        elif domain == "capital":
            payload.update(
                {
                    "equity": float(envelope.payload.get("equity", envelope.payload.get("account_equity", 0.0)) or 0.0),
                    "drawdown_pct": float(envelope.payload.get("drawdown_pct", 0.0) or 0.0),
                    "profit": float(envelope.payload.get("profit", envelope.payload.get("net_pnl", 0.0)) or 0.0),
                    "allocation": float(envelope.payload.get("allocation", 0.0) or 0.0),
                    "survivability_score": float(envelope.payload.get("survivability_score", 0.0) or 0.0),
                }
            )
        elif domain == "audit":
            payload.update(
                {
                    "system_state": str(envelope.payload.get("system_state", envelope.payload.get("status", "unknown")) or "unknown"),
                    "hard_invariants_status": str(envelope.payload.get("hard_invariants_status", "unknown") or "unknown"),
                    "drift_status": str(envelope.payload.get("drift_status", "unknown") or "unknown"),
                    "gate_status": str(envelope.payload.get("gate_status", "unknown") or "unknown"),
                    "readiness_stage": str(envelope.payload.get("readiness_stage", "unknown") or "unknown"),
                }
            )
        elif domain == "telemetry":
            payload.setdefault("events", envelope.payload.get("events", []))
        elif domain == "simulation":
            payload.setdefault("scenarios", envelope.payload.get("scenarios", []))
        return payload

    def _flush_telemetry_buffer(self, *, force: bool = False) -> None:
        now = time.time()
        if not self._telemetry_buffer:
            return
        if not force and (now - self._last_telemetry_flush) < self.telemetry_flush_s:
            return
        payload = {
            "type": "telemetry",
            "count": len(self._telemetry_buffer),
            "events": self._telemetry_buffer[-200:],
            "timestamp": time.time(),
        }
        self.bus.publish_ws(channel="telemetry", payload=payload)
        self._telemetry_buffer = []
        self._last_telemetry_flush = now

    def run_forever(self) -> None:
        LOGGER.info("universe_realtime_worker_start group=%s consumer=%s", self.consumer_group, self.consumer_name)
        streams = list(EVENT_STREAMS.values())
        self.bus.ensure_groups(streams=streams, group=self.consumer_group)

        while not self._stop.is_set():
            # Drain pending entries first to guarantee restart-safe at-least-once processing.
            rows = self.bus.consume_pending(
                stream_names=streams,
                group=self.consumer_group,
                consumer=self.consumer_name,
                count=100,
            )
            if not rows:
                rows = self.bus.consume(
                    stream_names=streams,
                    group=self.consumer_group,
                    consumer=self.consumer_name,
                    count=200,
                    block_ms=1000,
                )
            if not rows:
                self._flush_telemetry_buffer(force=False)
                continue

            for stream, msg_id, envelope in rows:
                domain = STREAM_TO_DOMAIN.get(stream)
                if not domain:
                    self.bus.ack(stream=stream, group=self.consumer_group, message_id=msg_id)
                    continue
                try:
                    inserted = self.store.append_event(stream=stream, envelope=envelope)
                    if inserted:
                        projection = self._build_projection_payload(domain=domain, envelope=envelope)
                        self.store.upsert_latest(domain=domain, payload=projection)

                        ws_channel = DOMAIN_TO_WS.get(domain)
                        if ws_channel:
                            ws_payload = {
                                "type": domain,
                                "event_type": envelope.event_type,
                                "symbol": envelope.symbol,
                                "confidence": envelope.confidence,
                                "timestamp": envelope.timestamp,
                                "payload": envelope.payload,
                            }
                            if ws_channel == "telemetry":
                                self._telemetry_buffer.append(ws_payload)
                                self._flush_telemetry_buffer(force=False)
                            else:
                                self.bus.publish_ws(channel=ws_channel, payload=ws_payload)
                finally:
                    self.bus.ack(stream=stream, group=self.consumer_group, message_id=msg_id)

        self._flush_telemetry_buffer(force=True)
        LOGGER.info("universe_realtime_worker_stop")


def run_worker_forever() -> int:
    logging.basicConfig(level=os.getenv("AUTONOMOUS_LOG_LEVEL", "INFO").upper())
    bus = UniverseEventBus.from_env()
    store = UniverseProjectionStore.from_env()
    worker = RealtimeProjectionWorker(
        bus=bus,
        store=store,
        consumer_group=str(os.getenv("AUTONOMOUS_UNIVERSE_RT_GROUP", "universe_realtime") or "universe_realtime"),
        consumer_name=str(os.getenv("AUTONOMOUS_UNIVERSE_RT_CONSUMER", "realtime-worker") or "realtime-worker"),
        telemetry_flush_s=float(os.getenv("AUTONOMOUS_UNIVERSE_TELEMETRY_FLUSH_S", "0.2") or "0.2"),
    )

    def _handle_signal(_sig: int, _frame: Any) -> None:
        worker.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    worker.run_forever()
    return 0
