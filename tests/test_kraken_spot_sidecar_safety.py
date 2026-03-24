import pytest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from autonomous_investment_robot.connectors.cex.kraken_spot import (
    KrakenSpotConnector,
    KrakenSpotConnectorError,
    KrakenSpotTradingBlocked,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_root_module(module_name: str, file_name: str):
    spec = spec_from_file_location(module_name, REPO_ROOT / file_name)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_kraken_spot_connector_requires_credentials(monkeypatch):
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    monkeypatch.delenv("KRAKEN_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_API_SECRET", raising=False)

    with pytest.raises(KrakenSpotConnectorError, match="missing_credentials"):
        KrakenSpotConnector()


def test_kraken_spot_connector_blocks_trading_calls():
    connector = object.__new__(KrakenSpotConnector)

    with pytest.raises(KrakenSpotTradingBlocked, match="kraken_spot_trading_unsupported_in_tracked_runtime"):
        connector.execute_margin_order("BTC/EUR", "buy", 20.0, 3.0)


def test_live_production_master_is_explicitly_blocked():
    live_production_master = _load_root_module("live_production_master", "live_production_master.py")

    with pytest.raises(RuntimeError, match="kraken_spot_live_sidecar_unsupported_use_launch_gated_runtime"):
        live_production_master.run_elite_bot()


def test_god_mode_launcher_is_explicitly_blocked():
    god_mode_launcher = _load_root_module("god_mode_launcher", "god_mode_launcher.py")

    with pytest.raises(RuntimeError, match="god_mode_launcher_unsupported_use_python_-m_autonomous_investment_robot"):
        god_mode_launcher.run_trading_loop()


def test_src_main_is_explicitly_blocked():
    src_main = _load_root_module("src_main_root", "src/main.py")

    with pytest.raises(SystemExit, match="legacy_root_entrypoint_unsupported_use_python_-m_autonomous_investment_robot"):
        src_main.main()


def test_dashboard_fails_closed_without_credentials():
    dashboard = _load_root_module("dashboard", "dashboard.py")

    client = dashboard.app.test_client()
    response = client.get("/")

    assert response.status_code == 503
    assert b"Kraken API unavailable: missing_credentials" in response.data
