from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from autonomous_investment_robot.config.settings import _load_yaml_like


IMMUTABLE_SAFETY_KEYS = {
    "AUTONOMOUS_PROFIT_TARGET_NET",
    "PROFIT_TARGET_NET",
    "AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS",
}

ENV_DIRECT_KEYS = {
    "AUTONOMOUS_HARD_CAP_NOTIONAL_QUOTE",
    "AUTONOMOUS_MIN_NOTIONAL_QUOTE",
    "AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS",
    "AUTONOMOUS_CONFIDENCE_THRESHOLD",
    "AUTONOMOUS_ORDER_CADENCE_S",
    "AUTONOMOUS_ADAPTIVE_HOLD_MULTIPLIER",
    "AUTONOMOUS_LIQUIDITY_NIGHT_EDGE_ADD_BPS",
    "AUTONOMOUS_USER_MIN_ORDER_QUOTE",
    "AUTONOMOUS_EXCHANGE_MIN_ORDER_QUOTE_FALLBACK",
    "AUTONOMOUS_MAX_OPEN_ORDERS_GLOBAL",
    "AUTONOMOUS_MAX_PARALLEL_TRADES",
    "AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE",
    "AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE_DEFAULT",
    "AUTONOMOUS_GUARDS_MODE",
    "AUTONOMOUS_LIVE_GO",
    "AUTONOMOUS_REQUIRE_OPERATOR_LIVE_CONFIRMATION",
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _resolve_run_dir(config_path: str) -> str:
    env_override = str(os.getenv("AUTONOMOUS_RUN_DIR", "") or "").strip()
    if env_override:
        return env_override
    try:
        cfg = _load_yaml_like(config_path)
        storage = cfg.get("storage", {}) if isinstance(cfg, dict) else {}
        value = storage.get("run_dir")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception:
        pass
    return "runs/kraken_spot_live"


def _override_path_for(config_path: str) -> Path:
    custom = str(os.getenv("AUTONOMOUS_CONFIG_OVERRIDE_PATH", "") or "").strip()
    if custom:
        return Path(custom)
    return Path(_resolve_run_dir(config_path)) / "override.yaml"


def _coerce_env_value(raw: str) -> Any:
    value = str(raw).strip()
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except Exception:
        return value


def _env_runtime_override() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ENV_DIRECT_KEYS:
        raw = os.getenv(key)
        if raw is None or not str(raw).strip():
            continue
        if key in IMMUTABLE_SAFETY_KEYS:
            continue
        out[key] = _coerce_env_value(raw)

    allowlist = str(os.getenv("AUTONOMOUS_UNIVERSE_ALLOWLIST", "") or "").strip()
    if allowlist:
        symbols = [s.strip() for s in allowlist.split(",") if s.strip()]
        if symbols:
            out["universe"] = symbols

    return out


def apply_runtime_override(config_path: str) -> str:
    cfg = _load_yaml_like(config_path)
    if not isinstance(cfg, dict):
        cfg = {}

    override_path = _override_path_for(config_path)
    merged = dict(cfg)
    if override_path.exists():
        try:
            raw = yaml.safe_load(override_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k in list(raw.keys()):
                    if str(k) in IMMUTABLE_SAFETY_KEYS:
                        raw.pop(k, None)
                env_map = raw.get("env")
                if isinstance(env_map, dict):
                    for ek, ev in env_map.items():
                        key = str(ek or "").strip()
                        if not key or key in IMMUTABLE_SAFETY_KEYS:
                            continue
                        os.environ[key] = str(ev)
                merged = _deep_merge(cfg, raw)
        except Exception:
            merged = dict(cfg)

    merged = _deep_merge(merged, _env_runtime_override())

    run_dir = Path(_resolve_run_dir(config_path))
    run_dir.mkdir(parents=True, exist_ok=True)
    effective_path = run_dir / "runtime_config.effective.yaml"
    effective_path.write_text(yaml.safe_dump(merged, sort_keys=False), encoding="utf-8")
    return str(effective_path)
