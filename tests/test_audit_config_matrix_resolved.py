from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "audit_config_matrix.py"
    spec = importlib.util.spec_from_file_location("audit_config_matrix", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_collect_config_matrix_resolves_harmony(tmp_path: Path) -> None:
    mod = _load_script_module()
    cfg = tmp_path / "config.paper.yaml"
    cfg.write_text(
        '{"mode":"paper","execution":{"mode":"paper","fee_bps":25.0,"slippage_bps":1.5},"policy":{"base_risk_budget":25.0},"risk":{"max_drawdown_pct":8.0}}',
        encoding="utf-8",
    )
    matrix = mod.collect_config_matrix([cfg], env={})
    rows = matrix["rows"]
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["sell_min_profit_bps"] >= 30.0
    assert rows[0]["config_drift_check_passed"] is True
    assert rows[0]["resolved_config_fingerprint"]
    assert "summary" in matrix
    assert int(matrix["summary"]["drift_failures"]) == 0
    assert matrix["freeze_contract"]["matrix_fingerprint"]
    md = mod.to_markdown(matrix)
    assert "| Config | Status | Mode | Provider | Cadence(s) | MinOrder | SellMinBps |" in md
