from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NON_PAPER_CONFIGS = [
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
