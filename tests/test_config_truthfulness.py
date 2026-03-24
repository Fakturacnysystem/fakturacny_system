from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NON_PAPER_CONFIGS = [
    "config.kraken_spot.tiny_live.yaml",
    "config.kraken_spot.live.yaml",
    "config.kraken_spot.live_profit.yaml",
    "config.kraken_spot.readonly_analysis.yaml",
    "config.kraken_derivatives.live.yaml",
    "config.kraken_derivatives.live_canary.yaml",
    "config.kraken_derivatives.live_readonly.yaml",
    "config.kraken_derivatives.testnet.yaml",
    "config.perps_intraday.live.yaml",
    "config.perps_intraday.live_canary.yaml",
    "config.perps_intraday.live_readonly.yaml",
    "config.perps_intraday.testnet.yaml",
]


def test_non_paper_configs_do_not_claim_top_level_paper_mode() -> None:
    for rel_path in NON_PAPER_CONFIGS:
        payload = json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
        assert payload["execution"]["mode"] != "paper"
        assert payload["mode"] == "live", rel_path


def test_kraken_spot_live_configs_are_committed_locked_by_default() -> None:
    for rel_path in ("config.kraken_spot.tiny_live.yaml", "config.kraken_spot.live.yaml", "config.kraken_spot.live_profit.yaml"):
        payload = json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
        unlock = payload["safety"]["live_unlock"]
        assert unlock["enable_live_trading"] is False, rel_path
        assert unlock["ack_i_understand_risks"] is False, rel_path
        assert unlock["allow_full_live_stage"] is False, rel_path


def test_kraken_spot_live_configs_start_in_normal_risk_mode() -> None:
    for rel_path in ("config.kraken_spot.tiny_live.yaml", "config.kraken_spot.live.yaml", "config.kraken_spot.live_profit.yaml"):
        payload = json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
        assert payload["safe_mode_default"] is False, rel_path


def test_kraken_spot_live_configs_truthfully_separate_tiny_limited_and_full_stage() -> None:
    tiny = json.loads((REPO_ROOT / "config.kraken_spot.tiny_live.yaml").read_text(encoding="utf-8"))
    limited = json.loads((REPO_ROOT / "config.kraken_spot.live.yaml").read_text(encoding="utf-8"))
    full_stage = json.loads((REPO_ROOT / "config.kraken_spot.live_profit.yaml").read_text(encoding="utf-8"))

    assert tiny["rollout_stage"] == "tiny_live"
    assert tiny["canary_mode"] is False
    assert limited["rollout_stage"] == "limited_live"
    assert limited["canary_mode"] is False
    assert full_stage["canary_mode"] is False


def test_tiny_live_config_is_stricter_than_normal_live() -> None:
    tiny = json.loads((REPO_ROOT / "config.kraken_spot.tiny_live.yaml").read_text(encoding="utf-8"))
    normal = json.loads((REPO_ROOT / "config.kraken_spot.live_profit.yaml").read_text(encoding="utf-8"))

    assert tiny["policy"]["base_risk_budget"] < normal["policy"]["base_risk_budget"]
    assert tiny["risk"]["max_position_notional"] < normal["risk"]["max_position_notional"]
    assert tiny["risk"]["max_exposure_notional"] < normal["risk"]["max_exposure_notional"]
    assert tiny["risk"]["max_orders_per_min"] <= normal["risk"]["max_orders_per_min"]
    assert tiny["risk"]["max_spread_bps"] <= normal["risk"]["max_spread_bps"]
