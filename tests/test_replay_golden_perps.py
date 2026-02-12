import json
from pathlib import Path

from autonomous_investment_robot.main import run_with_config


def test_replay_golden_perps_checksums_match():
    result = run_with_config("config.perps_intraday.paper.yaml")
    fixture = json.loads(Path("tests/fixtures/replay/golden_checksums_perps_intraday.json").read_text(encoding="utf-8"))
    assert result["orders_checksum"] == fixture["orders_checksum"]
    assert result["fills_checksum"] == fixture["fills_checksum"]
    assert result["equity_checksum"] == fixture["equity_checksum"]
