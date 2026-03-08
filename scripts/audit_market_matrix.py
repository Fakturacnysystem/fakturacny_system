#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import _load_yaml_like  # noqa: E402


def _read_config(path: Path) -> dict[str, Any]:
    try:
        payload = _load_yaml_like(str(path))
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


def collect_market_matrix(config_paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cfg_path in sorted(config_paths):
        cfg = _read_config(cfg_path)
        mode = str(cfg.get("mode", "") or "")
        execution = cfg.get("execution", {}) if isinstance(cfg.get("execution"), dict) else {}
        exec_mode = str(execution.get("mode", mode) or mode)
        provider = str(
            execution.get("provider")
            or execution.get("live_provider")
            or cfg.get("provider")
            or cfg.get("live_provider")
            or "paper_sim_provider"
        )
        universe = _as_list(cfg.get("universe", []))
        quote = ""
        if universe:
            head = universe[0].upper()
            if head.endswith("EUR"):
                quote = "EUR"
            elif head.endswith("USD") or head.endswith("USDT"):
                quote = "USD"
        leverage = (
            (cfg.get("risk", {}) if isinstance(cfg.get("risk"), dict) else {}).get("leverage")
            if isinstance(cfg.get("risk"), dict)
            else ""
        )
        market_type = "spot"
        provider_l = provider.lower()
        if "perp" in provider_l or "futures" in provider_l:
            market_type = "perps"
        try:
            config_label = str(cfg_path.relative_to(ROOT))
        except Exception:
            config_label = str(cfg_path)
        rows.append(
            {
                "config": config_label,
                "provider": provider,
                "market_type": market_type,
                "mode": exec_mode,
                "symbols": universe,
                "symbol_count": len(universe),
                "quote": quote,
                "leverage": leverage,
            }
        )
    return rows


def to_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Market Matrix",
        "",
        "| Config | Provider | Market | Mode | Symbols | Quote | Leverage |",
        "|---|---|---|---|---:|---|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['config']}` | `{row['provider']}` | `{row['market_type']}` | `{row['mode']}` | {int(row['symbol_count'])} | `{row['quote']}` | {row['leverage']} |"
        )
    lines.append("")
    lines.append("## Universe Details")
    lines.append("")
    for row in rows:
        lines.append(f"### `{row['config']}`")
        symbols = row.get("symbols", [])
        if symbols:
            lines.append("")
            lines.append("`" + ", ".join(str(s) for s in symbols[:200]) + "`")
        else:
            lines.append("")
            lines.append("_No symbols configured_")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-glob",
        default="config*.yaml",
        help="Glob pattern used from repo root.",
    )
    parser.add_argument(
        "--output",
        default="docs/market_matrix.md",
        help="Output markdown path.",
    )
    parser.add_argument(
        "--json-output",
        default="",
        help="Optional JSON output path.",
    )
    args = parser.parse_args()

    config_paths = [Path(p) for p in glob.glob(str(ROOT / args.config_glob))]
    rows = collect_market_matrix(config_paths)
    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(to_markdown(rows), encoding="utf-8")
    if str(args.json_output).strip():
        json_path = ROOT / str(args.json_output).strip()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"ok": True, "rows": len(rows), "output": str(out_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
