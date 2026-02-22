import json
from pathlib import Path

from autonomous_investment_robot.main import run_record, run_replay
from autonomous_investment_robot.main import request_kill


class FakePublicConnector:
    def __init__(self, _settings):
        self._agg_id = 100

    def book_ticker(self, symbol):
        return {"bidPrice": "100.0", "askPrice": "100.1", "bidQty": "10", "askQty": "11", "symbol": symbol}

    def premium_index(self, symbol):
        return {"markPrice": "100.05", "indexPrice": "100.0", "lastFundingRate": "0.0001", "time": 1700000000000}

    def agg_trades(self, symbol, limit=20):  # noqa: ARG002
        self._agg_id += 1
        return [
            {"a": self._agg_id, "p": "100.02", "q": "0.01", "T": 1700000000000 + self._agg_id, "m": False},
        ]


def test_record_then_replay_recordings_events_gt_zero(tmp_path, monkeypatch):
    cfg = {
        "mode": "paper",
        "provider_whitelist": ["binance_um_perps"],
        "universe": ["BTCUSDT"],
        "execution": {"mode": "live_readonly"},
        "risk": {
            "max_daily_loss_pct": 1.0,
            "max_drawdown_pct": 2.0,
            "max_position_notional": 10.0,
            "max_exposure_notional": 10.0,
            "max_orders_per_min": 5,
            "leverage": 0,
            "max_spread_bps": 10.0,
            "min_depth_notional": 10.0,
            "stale_data_seconds": 10.0,
            "min_margin_buffer": 2.0,
            "max_funding_cost_per_day": 1.0,
            "max_oi_spike_pct": 1.0,
            "max_liquidation_spike": 1.0,
            "divergence_threshold_bps": 10.0,
            "crowding_score_kill": 10.0,
        },
        "tco": {"max_total_cost_bps": 20.0, "max_impact_bps": 20.0},
        "storage": {"run_dir": str(tmp_path / "sample")},
        "fixtures": {"ohlcv_csv": "data/fixtures/perps/btcusdt_perp_5m.csv"},
    }
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr("autonomous_investment_robot.main.BinanceUMPerpsConnector", FakePublicConnector)

    out = run_record(str(cfg_path), run_id="sample", duration_seconds=1, poll_interval_seconds=0.2)
    assert out["events_recorded"] > 0
    assert out["recording_health"]["events"] > 0
    assert out["recording_index"]["events"] > 0
    assert out["recording_meta"]["schema_version"] == 1

    market = Path(cfg["storage"]["run_dir"]) / "recordings" / "sample" / "market.jsonl"
    assert market.exists()
    assert len([ln for ln in market.read_text(encoding="utf-8").splitlines() if ln.strip()]) > 0

    replay = run_replay(str(cfg_path), source="recordings")
    assert replay["events"] > 0
    assert replay["run_id"] == "sample"
    assert replay["recording_health"]["ok"] is True


def test_replay_recordings_latest_run_id_autodetect(tmp_path):
    base = tmp_path / "runs"
    r1 = base / "recordings" / "old"
    r2 = base / "recordings" / "new"
    r1.mkdir(parents=True)
    r2.mkdir(parents=True)
    (r1 / "market.jsonl").write_text("", encoding="utf-8")
    (r2 / "market.jsonl").write_text(
        '{"stream":"btcusdt@aggTrade","data":{"e":"aggTrade","s":"BTCUSDT","a":1,"E":1700000000000,"T":1700000000000,"p":"100","q":"0.1","m":false}}\n',
        encoding="utf-8",
    )
    (r2 / "market.index.json").write_text('{"events":1,"schema_version":1,"streams":{"btcusdt@aggTrade":1}}', encoding="utf-8")
    (r2 / "market.meta.json").write_text('{"schema_version":1,"format":"binance_ws_market_jsonl"}', encoding="utf-8")
    cfg = {
        "mode": "paper",
        "provider_whitelist": ["binance_um_perps"],
        "universe": ["BTCUSDT"],
        "execution": {"mode": "live_readonly"},
        "risk": {
            "max_daily_loss_pct": 1.0, "max_drawdown_pct": 2.0, "max_position_notional": 10.0, "max_exposure_notional": 10.0,
            "max_orders_per_min": 5, "leverage": 0, "max_spread_bps": 10.0, "min_depth_notional": 10.0, "stale_data_seconds": 10.0,
            "min_margin_buffer": 2.0, "max_funding_cost_per_day": 1.0, "max_oi_spike_pct": 1.0, "max_liquidation_spike": 1.0,
            "divergence_threshold_bps": 10.0, "crowding_score_kill": 10.0
        },
        "tco": {"max_total_cost_bps": 20.0, "max_impact_bps": 20.0},
        "storage": {"run_dir": str(base)},
        "fixtures": {"ohlcv_csv": "data/fixtures/perps/btcusdt_perp_5m.csv"},
    }
    cfg_path = tmp_path / "cfg2.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    replay = run_replay(str(cfg_path), source="recordings")
    assert replay["run_id"] == "new"
    assert replay["events"] > 0


def test_request_kill_writes_kill_marker(tmp_path):
    cfg = {
        "mode": "paper",
        "provider_whitelist": ["paper_sim_provider"],
        "risk": {
            "max_daily_loss_pct": 1.0, "max_drawdown_pct": 2.0, "max_position_notional": 10.0, "max_exposure_notional": 10.0,
            "max_orders_per_min": 5, "leverage": 0, "max_spread_bps": 10.0, "min_depth_notional": 10.0, "stale_data_seconds": 10.0,
            "min_margin_buffer": 2.0, "max_funding_cost_per_day": 1.0, "max_oi_spike_pct": 1.0, "max_liquidation_spike": 1.0,
            "divergence_threshold_bps": 10.0, "crowding_score_kill": 10.0
        },
        "tco": {"max_total_cost_bps": 20.0, "max_impact_bps": 20.0},
        "storage": {"run_dir": str(tmp_path / "killrun")},
        "fixtures": {"ohlcv_csv": "data/fixtures/perps/btcusdt_perp_5m.csv"},
    }
    cfg_path = tmp_path / "cfg_kill.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    out = request_kill(str(cfg_path), reason="test_kill")
    assert out["status"] == "kill_requested"
    kill_file = Path(out["kill_file"])
    assert kill_file.exists()
    assert "test_kill" in kill_file.read_text(encoding="utf-8")
