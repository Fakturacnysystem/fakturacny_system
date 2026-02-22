import json
from pathlib import Path

from autonomous_investment_robot.main import run_record, run_replay


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

    market = Path(cfg["storage"]["run_dir"]) / "recordings" / "sample" / "market.jsonl"
    assert market.exists()
    assert len([ln for ln in market.read_text(encoding="utf-8").splitlines() if ln.strip()]) > 0

    replay = run_replay(str(cfg_path), source="recordings")
    assert replay["events"] > 0

