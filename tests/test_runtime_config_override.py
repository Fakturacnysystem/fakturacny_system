from __future__ import annotations

import os
from pathlib import Path

from autonomous_investment_robot.cli_runtime_config import apply_runtime_override


def test_runtime_override_applies_env_but_keeps_immutable(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "config.yaml"
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg.write_text(f"storage:\n  run_dir: {run_dir}\nexecution:\n  mode: live\n", encoding="utf-8")

    override = run_dir / "override.yaml"
    override.write_text(
        "env:\n"
        "  AUTONOMOUS_SYMBOL_TOPK: 33\n"
        "  AUTONOMOUS_PROFIT_TARGET_NET: 0.01\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("AUTONOMOUS_SYMBOL_TOPK", raising=False)
    monkeypatch.delenv("AUTONOMOUS_PROFIT_TARGET_NET", raising=False)

    eff = apply_runtime_override(str(cfg))
    assert Path(eff).exists()
    assert os.getenv("AUTONOMOUS_SYMBOL_TOPK") == "33"
    assert os.getenv("AUTONOMOUS_PROFIT_TARGET_NET") in {None, ""}
