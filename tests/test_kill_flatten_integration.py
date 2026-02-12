import json
from pathlib import Path

from autonomous_investment_robot.main import run_with_config


def test_divergence_kill_triggers_flatten(tmp_path):
    cfg = json.loads(Path("config.perps_intraday.paper.yaml").read_text(encoding="utf-8"))
    cfg["risk"]["divergence_threshold_bps"] = 10.0
    cfg["storage"]["run_dir"] = str(tmp_path / "run")
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    result = run_with_config(str(cfg_path))
    fills = json.loads((tmp_path / "run" / "fills.json").read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert any(f.get("status") == "flattened" for f in fills)
