from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "gpt_control_plane.py"
    spec = importlib.util.spec_from_file_location("gpt_control_plane", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_apply_writes_env_and_suggestions_without_openai_key(monkeypatch, tmp_path):
    module = _load_module()
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)

    (run_dir / "audit.log").write_text(
        "\n".join(
            [
                json.dumps({"event_type": "live_exec", "payload": {"status": "submitted", "reason": "ok"}}),
                json.dumps({"event_type": "live_exec", "payload": {"status": "blocked", "reason": "rate_limit_cooldown"}}),
                json.dumps({"event_type": "risk_reject", "payload": {"reason": "position_notional_exceeded"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "event_bus.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"topic": "execution", "payload": {"x": 1}}),
                json.dumps({"topic": "execution", "payload": {"x": 2}}),
                json.dumps({"topic": "risk", "payload": {"x": 3}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "dashboard_snapshot.json").write_text(
        json.dumps(
            {
                "groups": {
                    "execution": {"fill_rate": 0.3},
                    "efficiency": {"cost_to_alpha_ratio_modeled": 0.9},
                    "market_data": {"quality": "ok"},
                    "governance": {"policy_violation_warn": 1},
                    "reliability": {"uptime": 0.99},
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "symbols_trade_candidates.txt").write_text("XBTUSD\nETHUSD\n", encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")

    def _fake_call_openai_with_schema(*, model: str, prompt_payload: dict):
        assert model
        assert "stats" in prompt_payload
        return {
            "overrides": {
                "AUTONOMOUS_MIN_NET_EDGE_BPS": "0.8",
                "AUTONOMOUS_MAX_ORDERS_PER_MIN": "12",
                "AUTONOMOUS_GUARDS_MODE": "fatal_only",
                "AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE": "0",
                "OPENAI_API_KEY": "should_not_be_written",
            },
            "universe": ["XBTUSD", "ETHUSD", "SOLUSD"],
            "config_patch": {
                "yaml_path": "config.kraken_spot.live_profit.yaml",
                "suggested_changes": {
                    "risk": {"max_orders_per_min": 12, "rate_limit_disable": True},
                    "policy": {"base_risk_budget": 6.5},
                },
            },
            "rationale": {
                "why": "Lower edge threshold while preserving risk guardrails.",
                "evidence": {"top_block_reasons": {"rate_limit_cooldown": 1}},
                "risks": ["Higher trade count may increase fees."],
            },
        }

    monkeypatch.setattr(module, "call_openai_with_schema", _fake_call_openai_with_schema)

    rc = module.main(["--run-dir", str(run_dir), "--apply"])
    assert rc == 0

    suggestions_path = run_dir / "gpt_suggestions.json"
    env_path = run_dir / "env_overrides.sh"
    assert suggestions_path.exists()
    assert env_path.exists()

    suggestions_raw = suggestions_path.read_text(encoding="utf-8")
    env_raw = env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" not in suggestions_raw
    assert "OPENAI_API_KEY" not in env_raw
    assert "sk-test-123" not in suggestions_raw
    assert "sk-test-123" not in env_raw
    assert "export AUTONOMOUS_MIN_NET_EDGE_BPS=0.8" in env_raw
    assert "export AUTONOMOUS_MAX_ORDERS_PER_MIN=12" in env_raw

    payload = json.loads(suggestions_raw)
    assert payload["overrides"]["AUTONOMOUS_MIN_NET_EDGE_BPS"] == "0.8"
    assert "OPENAI_API_KEY" not in payload["overrides"]
    assert "AUTONOMOUS_GUARDS_MODE" not in payload["overrides"]
    assert "AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE" not in payload["overrides"]
    assert payload["universe"] == ["XBTUSD", "ETHUSD"]
    assert payload["config_patch"]["suggested_changes"]["risk"]["max_orders_per_min"] == 12
    assert "rate_limit_disable" not in payload["config_patch"]["suggested_changes"]["risk"]
