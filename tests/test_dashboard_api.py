from __future__ import annotations

import json
from pathlib import Path

from autonomous_investment_robot.monitoring.dashboard import create_dashboard_app
from autonomous_investment_robot.services.storage import SQLiteStore


def test_dashboard_health_and_status_endpoints(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "runtime_health.json").write_text(json.dumps({"status": "running"}), encoding="utf-8")
    (run_dir / "dashboard_snapshot.json").write_text(json.dumps({"groups": {}}), encoding="utf-8")
    (run_dir / "audit.log").write_text(json.dumps({"event_type": "heartbeat", "payload": {}}) + "\n", encoding="utf-8")

    store = SQLiteStore(str(run_dir))
    store.record_position(
        symbol="XBTUSD",
        signed_qty=0.1,
        avg_entry_price=60000.0,
        mark_price=61000.0,
        unrealized_pnl_quote=100.0,
        realized_pnl_quote=0.0,
        payload={},
    )

    cfg = tmp_path / "config.yaml"
    cfg.write_text("storage:\n  run_dir: %s\n" % str(run_dir), encoding="utf-8")

    app = create_dashboard_app(run_dir=str(run_dir), config_path=str(cfg), live_mode=False)
    c = app.test_client()

    assert c.get("/health").status_code == 200
    assert c.get("/status").status_code == 200
    assert c.get("/positions").status_code == 200
    assert c.get("/audit-events").status_code == 200
    assert c.get("/ui").status_code == 200


def test_dashboard_live_config_blocks_immutable_updates(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / "config.yaml"
    cfg.write_text("storage:\n  run_dir: %s\n" % str(run_dir), encoding="utf-8")

    app = create_dashboard_app(run_dir=str(run_dir), config_path=str(cfg), live_mode=True)
    c = app.test_client()

    r = c.post("/config", json={"env": {"AUTONOMOUS_PROFIT_TARGET_NET": 0.01}})
    assert r.status_code == 403

    r2 = c.post("/config", json={"env": {"AUTONOMOUS_SYMBOL_TOPK": 40}})
    assert r2.status_code == 200
    payload = r2.get_json()
    assert payload["ok"] is True
