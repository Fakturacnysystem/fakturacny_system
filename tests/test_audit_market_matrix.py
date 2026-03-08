from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "audit_market_matrix.py"
    spec = importlib.util.spec_from_file_location("audit_market_matrix", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_market_matrix_collect_and_markdown(tmp_path: Path) -> None:
    mod = _load_script_module()
    cfg_a = tmp_path / "config.a.yaml"
    cfg_b = tmp_path / "config.b.yaml"
    cfg_a.write_text(
        '{"mode":"paper","execution":{"mode":"paper","provider":"kraken_spot"},"universe":["XBTEUR","ETHEUR"],"risk":{"leverage":1}}',
        encoding="utf-8",
    )
    cfg_b.write_text(
        '{"mode":"live","execution":{"mode":"live","provider":"kraken_futures"},"universe":["PI_XBTUSD"],"risk":{"leverage":2}}',
        encoding="utf-8",
    )
    rows = mod.collect_market_matrix([cfg_a, cfg_b])
    assert len(rows) == 2
    assert {row["market_type"] for row in rows} == {"spot", "perps"}
    md = mod.to_markdown(rows)
    assert "| Config | Provider | Market | Mode | Symbols | Quote | Leverage |" in md
    assert "PI_XBTUSD" in md
