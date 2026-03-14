from __future__ import annotations

import json

from autonomous_investment_robot.universe_gateway.run_registry import resolve_run_directory


def test_run_registry_prefers_live_target_when_requested(tmp_path) -> None:
    runs = tmp_path / "runs"
    latest = runs / "latest"
    paper = runs / "paper_default"
    live = runs / "kraken_spot_live"
    latest.mkdir(parents=True, exist_ok=True)
    paper.mkdir(parents=True, exist_ok=True)
    live.mkdir(parents=True, exist_ok=True)

    (latest / "health.json").write_text(json.dumps({"mode": "paper", "status": "ok"}), encoding="utf-8")
    (paper / "health.json").write_text(json.dumps({"mode": "paper", "status": "ok"}), encoding="utf-8")
    (live / "health.json").write_text(json.dumps({"mode": "paper", "status": "starting", "reason": "manual_gate_pending"}), encoding="utf-8")
    (live / "runtime_config.effective.yaml").write_text("mode: live\nexecution:\n  mode: live\n", encoding="utf-8")

    resolution = resolve_run_directory(run_dir=str(latest), selection_mode="live")

    assert resolution.run_path == live.resolve()
    assert resolution.target_mode == "live"
    assert resolution.runtime_mode == "paper"
