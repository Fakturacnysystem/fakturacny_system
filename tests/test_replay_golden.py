import json
from pathlib import Path

from autonomous_investment_robot.main import run_with_config


def test_replay_golden_checksums_match():
    result = run_with_config("config.paper.yaml")
    fixture = json.loads(Path("tests/fixtures/replay/golden_checksums.json").read_text(encoding="utf-8"))
    assert result["orders_checksum"] == fixture["orders_checksum"]
    assert result["fills_checksum"] == fixture["fills_checksum"]
    assert result["equity_checksum"] == fixture["equity_checksum"]
