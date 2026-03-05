from __future__ import annotations

from pathlib import Path

from autonomous_investment_robot.services.storage import SQLiteStore


def test_sqlite_store_module_events_and_violations(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "run"))
    store.record_module_event(module="mastermind", action="select", reason="ok", symbol="XBTUSD", payload={"score": 1.2})
    store.record_violation(module="profit_gate", rule="core_rule_1", reason="blocked", symbol="XBTUSD", payload={"min": 0.02})

    events = store.latest_module_events(limit=5)
    violations = store.latest_violations(limit=5)
    assert len(events) >= 1
    assert len(violations) >= 1
    h = store.health()
    assert h["module_events"] >= 1
    assert h["violations"] >= 1
