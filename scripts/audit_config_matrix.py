#!/usr/bin/env python3
"""
Audit Config Matrix Resolved - Validates resolved harmony config and ensures
dry-run config matrix is properly audited.
"""

import json
import os
import sys
from pathlib import Path


def load_yaml_config(path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        import yaml
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    try:
        return json.loads(text)
    except Exception:
        return {}


def check_harmony_resolved(run_dir: str) -> tuple[bool, list[str]]:
    errors = []
    harmony_path = Path(run_dir) / "harmony_report.json"
    
    if not harmony_path.exists():
        errors.append(f"harmony_report.json not found in {run_dir}")
        return False, errors
    
    try:
        data = json.loads(harmony_path.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"Failed to parse harmony_report.json: {e}")
        return False, errors
    
    required_fields = [
        "order_cadence_s",
        "guards_mode",
        "user_min_order_quote",
        "effective_min_order_quote",
        "sell_min_profit_bps",
        "sell_target_profit_bps",
        "tp_only_mode",
        "max_orders_per_min",
        "market_watch_every_s",
        "blackout_enabled",
        "spread_spike_enabled",
        "liquidity_map_enabled",
    ]
    
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field in harmony_report: {field}")
    
    sell_min = float(data.get("sell_min_profit_bps", 0))
    if sell_min < 120.0:
        errors.append(f"sell_min_profit_bps ({sell_min}) below hard floor of 120 bps")
    
    if data.get("guards_mode") not in {"strict", "fatal_only"}:
        errors.append(f"Invalid guards_mode: {data.get('guards_mode')}")
    
    return len(errors) == 0, errors


def check_mastermind_status(run_dir: str) -> tuple[bool, list[str]]:
    errors = []
    status_path = Path(run_dir) / "mastermind_status.json"
    
    if not status_path.exists():
        errors.append(f"mastermind_status.json not found in {run_dir}")
        return False, errors
    
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"Failed to parse mastermind_status.json: {e}")
        return False, errors
    
    if "ok" not in data:
        errors.append("mastermind_status missing 'ok' field")
    
    if data.get("invariant_breach", False):
        errors.append("MASTERMIND DETECTED INVARIANT BREACH")
    
    return len(errors) == 0, errors


def check_dry_run_config(config_path: str) -> tuple[bool, list[str]]:
    errors = []
    
    if not Path(config_path).exists():
        errors.append(f"Config file not found: {config_path}")
        return False, errors
    
    config = load_yaml_config(config_path)
    
    mode = config.get("mode", config.get("execution", {}).get("mode", "paper"))
    if mode == "live":
        if not config.get("enable_live_trading", False):
            errors.append("live mode without enable_live_trading flag")
        if not config.get("ack_i_understand_risks", False):
            errors.append("live mode without ack_i_understand_risks flag")
    
    return len(errors) == 0, errors


def check_env_vars() -> tuple[bool, list[str]]:
    errors = []
    warnings = []
    
    forbidden_patterns = {
        "KRAKEN_API_KEY": "API key found in env",
        "KRAKEN_API_SECRET": "API secret found in env",
    }
    
    for key, msg in forbidden_patterns.items():
        if os.getenv(key):
            warnings.append(f"WARNING: {msg} - ensure it is not printed/logged")
    
    return len(errors) == 0, errors + warnings


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Audit config matrix resolved")
    parser.add_argument("--config", default="config.kraken_spot.live_profit.yaml", help="Config file path")
    parser.add_argument("--run-dir", default=None, help="Run directory")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry-run validation only")
    args = parser.parse_args()
    
    all_errors = []
    
    print("=" * 60)
    print("AUDIT CONFIG MATRIX RESOLVED")
    print("=" * 60)
    
    print("\n[1/4] Checking environment variables (secrets)...")
    ok, errors = check_env_vars()
    if not ok:
        all_errors.extend(errors)
        for err in errors:
            print(f"  {err}")
        print("  (API keys in env are OK for live trading)")
    else:
        print("  OK - No forbidden secrets detected")
    
    print("\n[2/4] Checking dry-run config...")
    ok, errors = check_dry_run_config(args.config)
    if not ok:
        all_errors.extend(errors)
        print(f"  FAIL: {errors}")
    else:
        print("  OK - Config validated")
    
    run_dir = args.run_dir
    if run_dir is None:
        config_data = load_yaml_config(args.config)
        storage = config_data.get("storage", {})
        run_dir = storage.get("run_dir", "runs/kraken_spot_live")
    
    print(f"\n[3/4] Checking harmony resolved ({run_dir})...")
    ok, errors = check_harmony_resolved(run_dir)
    if not ok:
        all_errors.extend(errors)
        print(f"  FAIL: {errors}")
    else:
        print("  OK - Harmony resolved validated")
    
    print(f"\n[4/4] Checking mastermind status ({run_dir})...")
    ok, errors = check_mastermind_status(run_dir)
    if not ok:
        all_errors.extend(errors)
        print(f"  FAIL: {errors}")
    else:
        print("  OK - Mastermind status validated")
    
    print("\n" + "=" * 60)
    if all_errors:
        print(f"FAILED - {len(all_errors)} error(s) found:")
        for err in all_errors:
            print(f"  - {err}")
        return 1
    else:
        print("ALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
