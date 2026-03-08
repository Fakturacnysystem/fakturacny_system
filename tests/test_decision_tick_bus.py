from __future__ import annotations

import json
from pathlib import Path

from autonomous_investment_robot.services.reliability.bus import ReliabilityBus


def test_decision_tick_bus_idempotent_publish(tmp_path: Path) -> None:
    bus = ReliabilityBus(str(tmp_path))
    payload = {"symbol": "XBTUSD", "decision": {"action": "none", "reason": "no_intent"}}
    first = bus.publish("intent", payload, event_id="decision-XBTUSD-1", idempotency_key="decision-XBTUSD-1")
    second = bus.publish("intent", payload, event_id="decision-XBTUSD-1", idempotency_key="decision-XBTUSD-1")
    assert first is not None
    assert second is None
    lines = [ln for ln in (tmp_path / "event_bus.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event_id"] == "decision-XBTUSD-1"
