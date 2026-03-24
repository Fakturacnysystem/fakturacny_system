from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


def _stable_hash(data: dict[str, Any]) -> str:
    import json

    return sha256(json.dumps(data, sort_keys=True, default=str).encode("utf-8")).hexdigest()


@dataclass
class BaseEvent:
    ts: datetime
    event_type: str
    symbol: str
    venue: str
    seq: int
    payload: dict[str, Any]
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketEvent(BaseEvent):
    pass


@dataclass
class OrderIntentEvent(BaseEvent):
    idempotency_key: str


@dataclass
class OrderEvent(BaseEvent):
    idempotency_key: str


@dataclass
class FillEvent(BaseEvent):
    idempotency_key: str


@dataclass
class PositionEvent(BaseEvent):
    pass


@dataclass
class AccountEvent(BaseEvent):
    pass


@dataclass
class RiskEvent(BaseEvent):
    pass


@dataclass
class ComplianceEvent(BaseEvent):
    pass


@dataclass
class TruthEvent(BaseEvent):
    pass


@dataclass
class RecoveryEvent(BaseEvent):
    pass


def make_event(event_cls, event_type: str, symbol: str, venue: str, seq: int, payload: dict[str, Any], idempotency_key: str | None = None):
    ts = datetime.now(timezone.utc)
    core = {"ts": ts.isoformat(), "event_type": event_type, "symbol": symbol, "venue": venue, "seq": seq, "payload": payload}
    checksum = _stable_hash(core)
    if idempotency_key is None:
        return event_cls(ts=ts, event_type=event_type, symbol=symbol, venue=venue, seq=seq, payload=payload, checksum=checksum)
    return event_cls(ts=ts, event_type=event_type, symbol=symbol, venue=venue, seq=seq, payload=payload, checksum=checksum, idempotency_key=idempotency_key)


def make_idempotency_key(payload: dict[str, Any], run_id: str, sequence: int) -> str:
    return _stable_hash({"run_id": run_id, "sequence": sequence, "payload": payload})
