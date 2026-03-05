from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable


@dataclass
class BusEvent:
    seq: int
    topic: str
    event_id: str
    idempotency_key: str
    payload: dict[str, Any]
    attempts: int
    ts: str


class ReliabilityBus:
    def __init__(self, run_dir: str, max_attempts: int = 3) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max(1, int(max_attempts))
        self.log_path = self.run_dir / "event_bus.jsonl"
        self.dead_letter_path = self.run_dir / "event_bus_dead_letter.jsonl"
        self._events: list[BusEvent] = []
        self._acked_ids: set[str] = set()
        self._idempotency_seen: set[str] = set()
        self._seq = 0

    def publish(self, topic: str, payload: dict[str, Any], *, event_id: str, idempotency_key: str = "") -> BusEvent | None:
        idem = str(idempotency_key or event_id)
        if idem in self._idempotency_seen:
            return None
        self._idempotency_seen.add(idem)
        self._seq += 1
        ev = BusEvent(
            seq=self._seq,
            topic=topic,
            event_id=str(event_id),
            idempotency_key=idem,
            payload=dict(payload),
            attempts=0,
            ts=datetime.now(timezone.utc).isoformat(),
        )
        self._events.append(ev)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(ev), sort_keys=True, default=str) + "\n")
        return ev

    def drain(self, topic: str, handler: Callable[[dict[str, Any]], None]) -> tuple[int, int]:
        delivered = 0
        failed = 0
        for ev in self._events:
            if ev.topic != topic or ev.event_id in self._acked_ids:
                continue
            try:
                handler(ev.payload)
                self._acked_ids.add(ev.event_id)
                delivered += 1
            except Exception:
                ev.attempts += 1
                failed += 1
                if ev.attempts >= self.max_attempts:
                    with self.dead_letter_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(asdict(ev), sort_keys=True, default=str) + "\n")
                    self._acked_ids.add(ev.event_id)
        return delivered, failed

    def replay(self, topic: str | None = None) -> list[BusEvent]:
        if not self.log_path.exists():
            return []
        out: list[BusEvent] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            ev = BusEvent(
                seq=int(raw.get("seq", 0)),
                topic=str(raw.get("topic", "") or ""),
                event_id=str(raw.get("event_id", "") or ""),
                idempotency_key=str(raw.get("idempotency_key", "") or ""),
                payload=dict(raw.get("payload", {}) or {}),
                attempts=int(raw.get("attempts", 0) or 0),
                ts=str(raw.get("ts", "") or ""),
            )
            if topic is None or ev.topic == topic:
                out.append(ev)
        out.sort(key=lambda x: x.seq)
        return out
