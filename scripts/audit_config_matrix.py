#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import RobotSettings, _load_yaml_like  # noqa: E402
from autonomous_investment_robot.services.ops.harmony import HarmonyConfigResolver  # noqa: E402


DEFAULT_CONFIG_GLOB = "config*.yaml"
DEFAULT_JSON_OUTPUT = "docs/config_matrix.json"
DEFAULT_MD_OUTPUT = "docs/config_matrix.md"


def _safe_load_settings(path: Path) -> tuple[RobotSettings | None, str]:
    try:
        return RobotSettings.from_file(str(path)), ""
    except Exception as first_exc:
        try:
            payload = _load_yaml_like(str(path))
            if not isinstance(payload, dict):
                return None, str(first_exc)
            payload = dict(payload)
            exec_cfg = payload.get("execution", {})
            if not isinstance(exec_cfg, dict):
                exec_cfg = {}
            payload["mode"] = "paper"
            exec_cfg["mode"] = "paper"
            payload["execution"] = exec_cfg
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                tmp.write(json.dumps(payload))
                tmp_path = Path(tmp.name)
            try:
                return RobotSettings.from_file(str(tmp_path)), ""
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception:
            return None, str(first_exc)


def _harmony_resolve(settings: RobotSettings, env: dict[str, str]) -> dict[str, Any]:
    resolver = HarmonyConfigResolver()
    resolved = resolver.resolve(
        settings=settings,
        env_snapshot=env,
        exchange_min_quote_fallback=float(env.get("AUTONOMOUS_EXCHANGE_MIN_ORDER_QUOTE_FALLBACK", "2.0") or "2.0"),
        dry_run=True,
    )
    payload = resolved.to_dict()
    payload["invariant_sell_min_profit_ok"] = float(payload.get("sell_min_profit_bps", 0.0)) >= 120.0
    payload["collision_count"] = int(len(payload.get("collisions", [])))
    return payload


def _summarize_row(config_path: Path, settings: RobotSettings, resolved: dict[str, Any], status: str, error: str = "") -> dict[str, Any]:
    provider = settings.live_provider()
    execution_mode = str(getattr(settings.execution, "mode", settings.trading_mode.value))
    try:
        config_label = str(config_path.relative_to(ROOT))
    except Exception:
        config_label = str(config_path)
    return {
        "config": config_label,
        "status": status,
        "error": error,
        "mode": execution_mode,
        "provider": provider,
        "run_dir": str(getattr(settings.storage, "run_dir", "")),
        "universe_size": len(getattr(settings, "universe", [])),
        "llm_provider": str(getattr(settings.llm, "provider", "")),
        "llm_model_primary": str(getattr(settings.llm, "model_primary", "") or getattr(settings.llm, "model", "")),
        "llm_model_fallback": str(getattr(settings.llm, "model_fallback", "")),
        "enable_xstocks": bool(getattr(settings.market_coverage, "enable_xstocks", False)),
        "enable_xstocks_etf": bool(getattr(settings.market_coverage, "enable_xstocks_etf", False)),
        "mixed_universe_mode": bool(getattr(settings.market_coverage, "mixed_universe_mode", False)),
        "order_cadence_s": float(resolved.get("order_cadence_s", 0.0)),
        "guards_mode": str(resolved.get("guards_mode", "")),
        "user_min_order_quote": float(resolved.get("user_min_order_quote", 0.0)),
        "exchange_min_order_quote": float(resolved.get("exchange_min_order_quote", 0.0)),
        "effective_min_order_quote": float(resolved.get("effective_min_order_quote", 0.0)),
        "sell_min_profit_bps": float(resolved.get("sell_min_profit_bps", 0.0)),
        "sell_target_profit_bps": float(resolved.get("sell_target_profit_bps", 0.0)),
        "tp_only_mode": bool(resolved.get("tp_only_mode", False)),
        "max_orders_per_min": int(resolved.get("max_orders_per_min", 0)),
        "market_watch_every_s": float(resolved.get("market_watch_every_s", 0.0)),
        "blackout_enabled": bool(resolved.get("blackout_enabled", False)),
        "spread_spike_enabled": bool(resolved.get("spread_spike_enabled", False)),
        "liquidity_map_enabled": bool(resolved.get("liquidity_map_enabled", False)),
        "invariant_sell_min_profit_ok": bool(resolved.get("invariant_sell_min_profit_ok", False)),
        "collision_count": int(resolved.get("collision_count", 0)),
        "collisions": resolved.get("collisions", []),
    }


def collect_config_matrix(config_paths: list[Path], env: dict[str, str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for config_path in sorted(config_paths):
        settings, err = _safe_load_settings(config_path)
        if settings is None:
            rows.append(
                {
                    "config": str(config_path.relative_to(ROOT)),
                    "status": "error",
                    "error": err,
                }
            )
            continue
        resolved = _harmony_resolve(settings, env)
        rows.append(_summarize_row(config_path=config_path, settings=settings, resolved=resolved, status="ok"))

    ok_rows = [r for r in rows if r.get("status") == "ok"]
    return {
        "rows": rows,
        "summary": {
            "configs_total": len(rows),
            "configs_ok": len(ok_rows),
            "configs_error": len(rows) - len(ok_rows),
            "invariant_failures": len([r for r in ok_rows if not bool(r.get("invariant_sell_min_profit_ok", False))]),
            "total_collisions": int(sum(int(r.get("collision_count", 0)) for r in ok_rows)),
        },
    }


def to_markdown(matrix: dict[str, Any]) -> str:
    rows = matrix.get("rows", [])
    summary = matrix.get("summary", {})
    lines = [
        "# Config Matrix (Harmony Resolved)",
        "",
        "## Summary",
        "",
        f"- configs_total: {int(summary.get('configs_total', 0))}",
        f"- configs_ok: {int(summary.get('configs_ok', 0))}",
        f"- configs_error: {int(summary.get('configs_error', 0))}",
        f"- invariant_failures: {int(summary.get('invariant_failures', 0))}",
        f"- total_collisions: {int(summary.get('total_collisions', 0))}",
        "",
        "## Matrix",
        "",
        "| Config | Status | Mode | Provider | Cadence(s) | MinOrder | SellMinBps | SellTargetBps | Guards | Collisions |",
        "|---|---|---|---|---:|---:|---:|---:|---|---:|",
    ]
    for row in rows:
        if row.get("status") != "ok":
            lines.append(f"| `{row.get('config', '')}` | error |  |  |  |  |  |  |  |  |")
            continue
        lines.append(
            "| `{config}` | {status} | `{mode}` | `{provider}` | {cadence:.2f} | {min_order:.2f} | {sell_min:.1f} | {sell_target:.1f} | `{guards}` | {collisions} |".format(
                config=row["config"],
                status=row["status"],
                mode=row["mode"],
                provider=row["provider"],
                cadence=float(row["order_cadence_s"]),
                min_order=float(row["effective_min_order_quote"]),
                sell_min=float(row["sell_min_profit_bps"]),
                sell_target=float(row["sell_target_profit_bps"]),
                guards=row["guards_mode"],
                collisions=int(row["collision_count"]),
            )
        )
    lines.extend(
        [
            "",
            "## Collision Details",
            "",
        ]
    )
    for row in rows:
        if row.get("status") != "ok":
            continue
        collisions = list(row.get("collisions", []))
        if not collisions:
            continue
        lines.append(f"### `{row['config']}`")
        lines.append("")
        for col in collisions:
            key = str(col.get("key", ""))
            winner = str(col.get("winner", ""))
            losers = ", ".join(str(x) for x in list(col.get("losers", [])))
            lines.append(f"- `{key}` winner: `{winner}` losers: `{losers}`")
        lines.append("")
    return "\n".join(lines)


def write_outputs(matrix: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(matrix, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(to_markdown(matrix), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate harmony-resolved config matrix.")
    parser.add_argument("--config-glob", default=DEFAULT_CONFIG_GLOB, help="Glob evaluated from repo root.")
    parser.add_argument("--json-output", default=DEFAULT_JSON_OUTPUT, help="JSON output path from repo root.")
    parser.add_argument("--md-output", default=DEFAULT_MD_OUTPUT, help="Markdown output path from repo root.")
    args = parser.parse_args()

    config_paths = [Path(p) for p in glob.glob(str(ROOT / args.config_glob))]
    env: dict[str, str] = dict(os.environ)
    for secret_key in (
        "KRAKEN_API_KEY",
        "KRAKEN_API_SECRET",
        "EXCHANGE_API_KEY",
        "EXCHANGE_API_SECRET",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
    ):
        if secret_key in env:
            del env[secret_key]

    matrix = collect_config_matrix(config_paths=config_paths, env=env)
    json_path = ROOT / str(args.json_output)
    md_path = ROOT / str(args.md_output)
    write_outputs(matrix=matrix, json_path=json_path, md_path=md_path)
    print(
        json.dumps(
            {
                "ok": True,
                "configs": int(matrix["summary"]["configs_total"]),
                "errors": int(matrix["summary"]["configs_error"]),
                "json_output": str(json_path),
                "md_output": str(md_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
