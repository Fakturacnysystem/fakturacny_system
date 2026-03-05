#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    yaml = None


DEFAULT_RUN_DIR = "runs/kraken_spot_live"
DEFAULT_MODEL = "gpt-5.2"
RESERVED_ENV_KEYS = {"OPENAI_API_KEY"}
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALLOWED_OVERRIDE_ENVS = {
    "AUTONOMOUS_MIN_NET_EDGE_BPS",
    "AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO",
    "AUTONOMOUS_MAX_ORDERS_PER_MIN",
    "AUTONOMOUS_RATE_LIMIT_COOLDOWN_S",
    "AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S",
    "AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE",
    "AUTONOMOUS_GROWTH_MAX_FRACTION",
    "AUTONOMOUS_SELF_TUNER_MIN_SAMPLES",
    "AUTONOMOUS_SELF_TUNER_EVERY_STEPS",
    "AUTONOMOUS_CANARY_FRACTION",
    "AUTONOMOUS_PROMOTED_FRACTION",
}
FORBIDDEN_OVERRIDE_KEYS = {
    "AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE",
    "AUTONOMOUS_KRAKEN_RATE_LIMIT_STORM",
    "AUTONOMOUS_GUARDS_MODE",
    "AUTONOMOUS_WALK_FORWARD_ENFORCE",
}
FORBIDDEN_CONFIG_KEY_TOKENS = {
    "kill",
    "kill_switch",
    "min_notional",
    "min_order",
    "rate_limit",
    "disable",
}


SUGGESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["overrides", "universe", "config_patch", "rationale"],
    "properties": {
        "overrides": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "universe": {
            "type": "array",
            "items": {"type": "string"},
        },
        "config_patch": {
            "type": "object",
            "additionalProperties": False,
            "required": ["yaml_path", "suggested_changes"],
            "properties": {
                "yaml_path": {"type": "string"},
                "suggested_changes": {"type": "object", "additionalProperties": True},
            },
        },
        "rationale": {
            "type": "object",
            "additionalProperties": False,
            "required": ["why", "evidence", "risks"],
            "properties": {
                "why": {"type": "string"},
                "evidence": {"type": "object", "additionalProperties": True},
                "risks": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
    },
}


@dataclass
class ArtifactSummary:
    run_dir: str
    audit_path: str
    dashboard_path: str
    event_bus_path: str
    constraints_path: str
    audit_lines_read: int
    event_bus_lines_read: int
    topic_counts: dict[str, int]
    top_block_reasons: dict[str, int]
    live_exec_counts: dict[str, int]
    kpi_groups: dict[str, dict[str, Any]]
    constraints_sample: dict[str, Any]

    def as_prompt_payload(self) -> dict[str, Any]:
        return {
            "run_dir": self.run_dir,
            "paths": {
                "audit_log": self.audit_path,
                "dashboard_snapshot": self.dashboard_path,
                "event_bus": self.event_bus_path,
                "exchange_constraints": self.constraints_path,
            },
            "stats": {
                "audit_lines_read": self.audit_lines_read,
                "event_bus_lines_read": self.event_bus_lines_read,
                "topic_counts": self.topic_counts,
                "top_block_reasons": self.top_block_reasons,
                "live_exec_counts": self.live_exec_counts,
            },
            "kpi_summary": self.kpi_groups,
            "exchange_constraints_sample": self.constraints_sample,
        }


def _eprint_event(event: str, **kwargs: Any) -> None:
    payload: dict[str, Any] = {"event": event}
    payload.update(kwargs)
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


def _tail_jsonl(path: Path, max_lines: int) -> list[dict[str, Any]]:
    if max_lines <= 0 or not path.exists():
        return []
    lines: deque[str] = deque(maxlen=max_lines)
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            lines.append(line.rstrip("\n"))
    out: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_yaml_like(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        try:
            payload = yaml.safe_load(text)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_kpi_groups(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = snapshot.get("groups", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(groups, dict):
        groups = {}
    wanted = ["execution", "efficiency", "market_data", "governance", "reliability"]
    out: dict[str, dict[str, Any]] = {}
    for group_name in wanted:
        group_payload = groups.get(group_name, {})
        out[group_name] = group_payload if isinstance(group_payload, dict) else {}
    return out


def _summarize_audit_events(events: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    reason_counts: Counter[str] = Counter()
    live_exec_counts: Counter[str] = Counter({"submitted": 0, "blocked": 0, "rejected": 0})
    for row in events:
        payload = row.get("payload")
        if isinstance(payload, dict):
            reason = payload.get("reason")
            if isinstance(reason, str) and reason.strip():
                reason_counts[reason.strip()] += 1
        if row.get("event_type") == "live_exec":
            status = ""
            if isinstance(payload, dict):
                raw_status = payload.get("status", "")
                if isinstance(raw_status, str):
                    status = raw_status.strip().lower()
            if status in {"submitted", "blocked", "rejected"}:
                live_exec_counts[status] += 1
    return dict(reason_counts.most_common(20)), dict(live_exec_counts)


def _summarize_event_bus(path: Path) -> tuple[dict[str, int], int]:
    if not path.exists():
        return {}, 0
    topic_counts: Counter[str] = Counter()
    parsed_rows = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            topic = payload.get("topic")
            if isinstance(topic, str) and topic.strip():
                topic_counts[topic.strip()] += 1
            else:
                topic_counts["?"] += 1
            parsed_rows += 1
    return dict(topic_counts), parsed_rows


def resolve_run_dir(run_dir_arg: str | None, config_path: Path | None) -> Path:
    if run_dir_arg:
        return Path(run_dir_arg).expanduser()
    if config_path and config_path.exists():
        cfg = _read_yaml_like(config_path)
        storage = cfg.get("storage", {})
        if isinstance(storage, dict):
            run_dir = storage.get("run_dir")
            if isinstance(run_dir, str) and run_dir.strip():
                return Path(run_dir.strip()).expanduser()
    return Path(DEFAULT_RUN_DIR)


def summarize_artifacts(run_dir: Path, audit_lines: int) -> ArtifactSummary:
    audit_path = run_dir / "audit.log"
    dashboard_path = run_dir / "dashboard_snapshot.json"
    event_bus_path = run_dir / "event_bus.jsonl"
    constraints_path = run_dir / "exchange_constraints.json"

    audit_events = _tail_jsonl(audit_path, audit_lines)
    top_block_reasons, live_exec_counts = _summarize_audit_events(audit_events)
    topic_counts, event_bus_lines = _summarize_event_bus(event_bus_path)
    kpi_groups = _extract_kpi_groups(_read_json(dashboard_path))
    constraints_payload = _read_json(constraints_path)
    constraints_sample: dict[str, Any] = {}
    cdict = constraints_payload.get("constraints", {}) if isinstance(constraints_payload, dict) else {}
    if isinstance(cdict, dict):
        for k in sorted(cdict.keys())[:8]:
            constraints_sample[k] = cdict.get(k)
    return ArtifactSummary(
        run_dir=str(run_dir),
        audit_path=str(audit_path),
        dashboard_path=str(dashboard_path),
        event_bus_path=str(event_bus_path),
        constraints_path=str(constraints_path),
        audit_lines_read=len(audit_events),
        event_bus_lines_read=event_bus_lines,
        topic_counts=topic_counts,
        top_block_reasons=top_block_reasons,
        live_exec_counts=live_exec_counts,
        kpi_groups=kpi_groups,
        constraints_sample=constraints_sample,
    )


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", "") or ""
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    try:
        output_items = getattr(response, "output", None)
        if not isinstance(output_items, list):
            return ""
        pieces: list[str] = []
        for item in output_items:
            contents = getattr(item, "content", None)
            if not isinstance(contents, list):
                continue
            for content in contents:
                text = getattr(content, "text", None)
                if isinstance(text, str) and text:
                    pieces.append(text)
        return "".join(pieces)
    except Exception:
        return ""


def call_openai_with_schema(*, model: str, prompt_payload: dict[str, Any]) -> dict[str, Any]:
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on runtime env
        raise SystemExit("Missing dependency: openai. Install with `pip install -r requirements.txt`.") from exc

    client = OpenAI()
    instructions = (
        "You are a trading bot control-plane advisor with strict safety policy. "
        "Return only valid JSON that exactly matches the provided schema. "
        "Do not include markdown. Do not include explanations outside JSON. "
        "Allowed overrides only: AUTONOMOUS_MIN_NET_EDGE_BPS, AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO, "
        "AUTONOMOUS_MAX_ORDERS_PER_MIN, AUTONOMOUS_RATE_LIMIT_COOLDOWN_S, AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S, "
        "AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE, AUTONOMOUS_GROWTH_MAX_FRACTION, "
        "AUTONOMOUS_SELF_TUNER_MIN_SAMPLES, AUTONOMOUS_SELF_TUNER_EVERY_STEPS, "
        "AUTONOMOUS_CANARY_FRACTION, AUTONOMOUS_PROMOTED_FRACTION. "
        "Never disable kill switch, never disable min-notional protection, never disable rate-limit protection. "
        "Universe must stay inside top-liquidity whitelist when provided."
    )
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=[
            {
                "role": "user",
                "content": (
                    "Analyze the local trading artifacts summary and suggest safe env overrides, "
                    "universe updates, and config patch hints.\n"
                    f"{json.dumps(prompt_payload, ensure_ascii=False)}"
                ),
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "gpt_bot_tuning",
                "schema": SUGGESTION_SCHEMA,
                "strict": True,
            }
        },
    )
    output_text = _extract_response_text(response)
    if not output_text.strip():
        raise RuntimeError("OpenAI response did not include structured JSON output.")
    parsed = json.loads(output_text)
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI response JSON root must be an object.")
    return parsed


def _scrub_openai_markers(value: Any, openai_key_value: str) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if str(k).upper() in RESERVED_ENV_KEYS:
                continue
            out[str(k)] = _scrub_openai_markers(v, openai_key_value)
        return out
    if isinstance(value, list):
        return [_scrub_openai_markers(v, openai_key_value) for v in value]
    if isinstance(value, str):
        clean = value.replace("OPENAI_API_KEY", "REDACTED_OPENAI_ENV")
        if openai_key_value:
            clean = clean.replace(openai_key_value, "[REDACTED]")
        return clean
    return value


def sanitize_overrides(raw: Any, openai_key_value: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        env_name = str(key).strip()
        if not env_name:
            continue
        if env_name.upper() in RESERVED_ENV_KEYS:
            continue
        if env_name in FORBIDDEN_OVERRIDE_KEYS:
            continue
        if env_name not in ALLOWED_OVERRIDE_ENVS:
            continue
        if not ENV_NAME_RE.match(env_name):
            continue
        env_val = _scrub_openai_markers(str(value), openai_key_value)
        out[env_name] = _clamp_override(env_name, str(env_val))
    return out


def _clamp_override(name: str, value: str) -> str:
    def _clamp_float(v: str, lo: float, hi: float, default: float) -> str:
        try:
            x = float(v)
        except Exception:
            x = float(default)
        x = max(lo, min(hi, x))
        return f"{x:.6g}"

    def _clamp_int(v: str, lo: int, hi: int, default: int) -> str:
        try:
            x = int(float(v))
        except Exception:
            x = int(default)
        x = max(lo, min(hi, x))
        return str(x)

    if name == "AUTONOMOUS_MIN_NET_EDGE_BPS":
        return _clamp_float(value, 0.1, 5.0, 1.0)
    if name == "AUTONOMOUS_MAX_COST_TO_ALPHA_RATIO":
        return _clamp_float(value, 0.1, 5.0, 1.5)
    if name == "AUTONOMOUS_MAX_ORDERS_PER_MIN":
        return _clamp_int(value, 1, 200, 20)
    if name in {"AUTONOMOUS_RATE_LIMIT_COOLDOWN_S", "AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S"}:
        return _clamp_float(value, 1.0, 30.0, 5.0)
    if name == "AUTONOMOUS_MAX_ORDER_NOTIONAL_QUOTE":
        return _clamp_float(value, 0.1, 1_000_000.0, 100.0)
    if name == "AUTONOMOUS_GROWTH_MAX_FRACTION":
        return _clamp_float(value, 0.05, 1.0, 0.5)
    if name == "AUTONOMOUS_SELF_TUNER_MIN_SAMPLES":
        return _clamp_int(value, 1, 10000, 30)
    if name == "AUTONOMOUS_SELF_TUNER_EVERY_STEPS":
        return _clamp_int(value, 1, 10000, 20)
    if name == "AUTONOMOUS_CANARY_FRACTION":
        return _clamp_float(value, 0.05, 1.0, 0.2)
    if name == "AUTONOMOUS_PROMOTED_FRACTION":
        return _clamp_float(value, 0.1, 1.0, 1.0)
    return value


def _read_symbol_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        sym = line.strip().upper()
        if sym and sym not in out:
            out.append(sym)
    return out


def _top_liquidity_whitelist(run_dir: Path) -> list[str]:
    candidates = _read_symbol_file(run_dir / "symbols_trade_candidates.txt")
    if candidates:
        return candidates
    return _read_symbol_file(run_dir / "symbols_watch_1000.txt")


def sanitize_universe(raw: Any, *, run_dir: Path, config_path: Path | None) -> list[str]:
    requested: list[str] = []
    if isinstance(raw, list):
        for row in raw:
            sym = str(row).strip().upper()
            if sym and sym not in requested:
                requested.append(sym)
    whitelist = _top_liquidity_whitelist(run_dir)
    if not whitelist and config_path and config_path.exists():
        cfg = _read_yaml_like(config_path)
        cfg_uni = cfg.get("universe", [])
        if isinstance(cfg_uni, list):
            for row in cfg_uni:
                sym = str(row).strip().upper()
                if sym and sym not in whitelist:
                    whitelist.append(sym)
    if whitelist:
        wl_set = set(whitelist)
        requested = [s for s in requested if s in wl_set]
    max_items = max(1, int(os.getenv("AUTONOMOUS_CONTROL_PLANE_UNIVERSE_MAX", "12") or "12"))
    return requested[:max_items]


def _filter_config_changes(obj: Any, key_path: str = "") -> Any:
    if not isinstance(obj, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in obj.items():
        ks = str(key).strip()
        if not ks:
            continue
        full = f"{key_path}.{ks}" if key_path else ks
        lowered = full.lower()
        if any(tok in lowered for tok in FORBIDDEN_CONFIG_KEY_TOKENS):
            continue
        if isinstance(value, dict):
            child = _filter_config_changes(value, full)
            if child:
                out[ks] = child
            continue
        # Strict control-plane policy: keep config patch minimal and only for max_orders/risk budget families.
        if full in {"risk.max_orders_per_min", "policy.base_risk_budget"}:
            out[ks] = value
    return out


def sanitize_config_patch(raw: Any, *, default_yaml_path: str) -> dict[str, Any]:
    patch = raw if isinstance(raw, dict) else {}
    yaml_path = patch.get("yaml_path")
    yaml_path_str = str(yaml_path).strip() if isinstance(yaml_path, str) else default_yaml_path
    suggested_changes = _filter_config_changes(patch.get("suggested_changes", {}))
    return {
        "yaml_path": yaml_path_str or default_yaml_path,
        "suggested_changes": suggested_changes if isinstance(suggested_changes, dict) else {},
    }


def build_env_exports(overrides: dict[str, str]) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "# Auto-generated by scripts/gpt_control_plane.py",
    ]
    for key in sorted(overrides):
        lines.append(f"export {key}={shlex.quote(overrides[key])}")
    return "\n".join(lines) + "\n"


def run_control_plane(args: argparse.Namespace) -> dict[str, Any]:
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key.strip():
        raise SystemExit("OPENAI_API_KEY is required. Export it first, then re-run the control plane.")

    config_path = Path(args.config).expanduser() if args.config else None
    run_dir = resolve_run_dir(args.run_dir, config_path)
    summary = summarize_artifacts(run_dir, audit_lines=args.audit_lines)
    _eprint_event(
        "control_plane_summary",
        run_dir=str(run_dir),
        audit_lines=summary.audit_lines_read,
        event_bus_lines=summary.event_bus_lines_read,
    )

    model = args.model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    raw_suggestion = call_openai_with_schema(model=model, prompt_payload=summary.as_prompt_payload())
    sanitized = _scrub_openai_markers(raw_suggestion, openai_key)
    if not isinstance(sanitized, dict):
        raise RuntimeError("Sanitized suggestion payload is not an object.")
    sanitized["overrides"] = sanitize_overrides(sanitized.get("overrides", {}), openai_key)
    sanitized["universe"] = sanitize_universe(
        sanitized.get("universe", []),
        run_dir=run_dir,
        config_path=config_path,
    )
    sanitized["config_patch"] = sanitize_config_patch(
        sanitized.get("config_patch", {}),
        default_yaml_path=args.config,
    )
    return {"run_dir": run_dir, "payload": sanitized}


def write_outputs(run_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    suggestions_path = run_dir / "gpt_suggestions.json"
    overrides_path = run_dir / "env_overrides.sh"

    suggestions_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    overrides_text = build_env_exports(payload.get("overrides", {}))
    overrides_path.write_text(overrides_text, encoding="utf-8")
    return suggestions_path, overrides_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GPT control plane for local bot artifact analysis.")
    parser.add_argument("--config", default="config.kraken_spot.live_profit.yaml", help="Path to robot YAML config.")
    parser.add_argument("--run-dir", default=None, help="Override run directory (otherwise from config storage.run_dir).")
    parser.add_argument("--audit-lines", type=int, default=2000, help="How many recent audit.log lines to analyze.")
    parser.add_argument("--model", default=None, help=f"OpenAI model to use (default env OPENAI_MODEL or {DEFAULT_MODEL}).")
    parser.set_defaults(dry_run=True)
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Print JSON suggestions (default).")
    parser.add_argument("--apply", dest="dry_run", action="store_false", help="Write run_dir/env_overrides.sh and gpt_suggestions.json.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_control_plane(args)
    run_dir: Path = result["run_dir"]
    payload: dict[str, Any] = result["payload"]

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        _eprint_event("control_plane_dry_run", run_dir=str(run_dir), apply=False)
        return 0

    suggestions_path, overrides_path = write_outputs(run_dir, payload)
    _eprint_event(
        "control_plane_written",
        run_dir=str(run_dir),
        suggestions_path=str(suggestions_path),
        overrides_path=str(overrides_path),
        apply=True,
    )
    print(json.dumps({"run_dir": str(run_dir), "suggestions_path": str(suggestions_path), "overrides_path": str(overrides_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
