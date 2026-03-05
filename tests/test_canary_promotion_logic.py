from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_promote_canary_writes_last_good_when_kpis_pass(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    promote = _load_script_module("promote_canary_script", repo_root / "scripts" / "promote_canary.py")
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "env_overrides.sh").write_text(
        "#!/usr/bin/env bash\nexport AUTONOMOUS_MIN_NET_EDGE_BPS=\"0.9\"\nexport AUTONOMOUS_MAX_ORDERS_PER_MIN=\"12\"\n",
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(
        json.dumps(
            {
                "groups": {
                    "execution": {"executions_submitted_total": 20.0, "reject_rate": 0.1},
                    "efficiency": {"cost_to_alpha_ratio_modeled": 0.7},
                    "performance": {"net_pnl_after_fees": 1.5},
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "audit.log").write_text("", encoding="utf-8")

    rc = promote.main(["--run-dir", str(run_dir)])
    assert rc == 0
    assert (run_dir / "last_good_overrides.json").exists()
    assert (run_dir / "promote_main.marker").exists()

    payload = json.loads((run_dir / "last_good_overrides.json").read_text(encoding="utf-8"))
    assert payload["source"] == "promote_canary"
    assert payload["overrides"]["AUTONOMOUS_MIN_NET_EDGE_BPS"] == "0.9"


def test_promote_canary_holds_when_gate_fails(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    promote = _load_script_module("promote_canary_script_hold", repo_root / "scripts" / "promote_canary.py")
    run_dir = tmp_path / "run_hold"
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "env_overrides.sh").write_text("export AUTONOMOUS_MIN_NET_EDGE_BPS=\"1.0\"\n", encoding="utf-8")
    (run_dir / "dashboard_snapshot.json").write_text(
        json.dumps(
            {
                "groups": {
                    "execution": {"executions_submitted_total": 15.0, "reject_rate": 0.95},
                    "efficiency": {"cost_to_alpha_ratio_modeled": 0.9},
                    "performance": {"net_pnl_after_fees": 1.0},
                }
            }
        ),
        encoding="utf-8",
    )

    rc = promote.main(["--run-dir", str(run_dir)])
    assert rc == 0
    assert not (run_dir / "last_good_overrides.json").exists()
    assert not (run_dir / "promote_main.marker").exists()

