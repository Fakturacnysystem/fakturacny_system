from __future__ import annotations

from pathlib import Path
import pytest

from autonomous_investment_robot.config.settings import _load_yaml_like


def _load_live_profit_config() -> dict:
    root = Path(__file__).resolve().parents[1]
    return _load_yaml_like(str(root / "config.kraken_spot.live_profit.yaml"))


def _load_config(path: str) -> dict:
    root = Path(__file__).resolve().parents[1]
    return _load_yaml_like(str(root / path))


def _assert_symbol_fixture_coverage(config_path: str) -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = _load_config(config_path)
    universe = [str(sym) for sym in cfg.get("universe", []) if str(sym)]
    fixtures = cfg.get("fixtures", {}) if isinstance(cfg.get("fixtures"), dict) else {}
    symbol_files = fixtures.get("symbol_files", {}) if isinstance(fixtures.get("symbol_files"), dict) else {}
    if len(universe) <= 1:
        return
    missing = [symbol for symbol in universe if symbol not in symbol_files]
    assert not missing, f"missing_symbol_fixtures_for_{config_path}:{','.join(missing)}"
    for symbol in universe:
        fixture_path = root / str(symbol_files[symbol])
        assert fixture_path.exists(), f"fixture_missing_for_{config_path}:{symbol}"


def test_live_profit_symbol_fixture_mapping_covers_universe() -> None:
    _assert_symbol_fixture_coverage("config.kraken_spot.live_profit.yaml")


def test_live_profit_symbol_fixtures_are_bounded_and_parseable() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = _load_live_profit_config()
    fixtures = cfg.get("fixtures", {}) if isinstance(cfg.get("fixtures"), dict) else {}
    symbol_files = fixtures.get("symbol_files", {}) if isinstance(fixtures.get("symbol_files"), dict) else {}

    required_columns = {"ts", "open", "high", "low", "close", "volume"}
    for symbol, rel_path in symbol_files.items():
        fixture_path = root / str(rel_path)
        lines = fixture_path.read_text(encoding="utf-8").splitlines()
        assert 2 <= len(lines) <= 200, f"fixture_size_out_of_bounds_for_{symbol}"
        header = {col.strip() for col in lines[0].split(",")}
        assert required_columns.issubset(header), f"fixture_columns_invalid_for_{symbol}"


@pytest.mark.parametrize(
    "config_path",
    [
        "config.kraken_spot.live.yaml",
        "config.kraken_spot.live_canary.yaml",
        "config.kraken_spot.live_readonly.yaml",
    ],
)
def test_safe_validation_configs_have_symbol_fixture_coverage(config_path: str) -> None:
    _assert_symbol_fixture_coverage(config_path)
