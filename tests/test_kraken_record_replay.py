import json

from autonomous_investment_robot.main import run_record, run_replay


class _FakePoller:
    def __init__(self, *args, **kwargs):
        pass

    def record(self, run_id: str, duration_seconds: int, poll_interval_seconds: float = 1.0):
        return {"events_recorded": 2, "record_path": "tmp"}


def test_record_duration_writes_events(tmp_path, monkeypatch):
    cfg = {
        "mode": "live",
        "provider_whitelist": ["kraken_spot"],
        "universe": ["XBTUSD"],
        "execution": {"mode": "live_readonly"},
        "risk": {
            "max_daily_loss_pct": 1.0, "max_drawdown_pct": 2.0, "max_position_notional": 1.0, "max_exposure_notional": 1.0,
            "max_orders_per_min": 1, "leverage": 0, "max_spread_bps": 1.0, "min_depth_notional": 0.0, "stale_data_seconds": 1.0,
            "min_margin_buffer": 1.0, "max_funding_cost_per_day": 0.0, "max_oi_spike_pct": 0.0, "max_liquidation_spike": 0.0,
            "divergence_threshold_bps": 1.0, "crowding_score_kill": 1.0
        },
        "tco": {"max_total_cost_bps": 1.0, "max_impact_bps": 1.0},
        "storage": {"run_dir": str(tmp_path / "runs")},
    }
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr("autonomous_investment_robot.main.KrakenSpotMarketPoller", _FakePoller)
    out = run_record(str(p), run_id="r1", duration_seconds=1)
    assert out["events_recorded"] == 2


def test_replay_recordings_events_gt_zero(tmp_path):
    run_dir = tmp_path / "runs" / "recordings" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "market.jsonl").write_text('{"stream":"xbtusd@ticker","data":{"e":"ticker","s":"XBTUSD","E":1700000000000,"p":"100","q":"1"}}\n', encoding="utf-8")
    cfg = {
        "mode": "paper",
        "provider_whitelist": ["paper_sim_provider"],
        "universe": ["XBTUSD"],
        "execution": {"mode": "paper"},
        "risk": {
            "max_daily_loss_pct": 1.0, "max_drawdown_pct": 2.0, "max_position_notional": 1.0, "max_exposure_notional": 1.0,
            "max_orders_per_min": 1, "leverage": 0, "max_spread_bps": 1.0, "min_depth_notional": 0.0, "stale_data_seconds": 1.0,
            "min_margin_buffer": 1.0, "max_funding_cost_per_day": 0.0, "max_oi_spike_pct": 0.0, "max_liquidation_spike": 0.0,
            "divergence_threshold_bps": 1.0, "crowding_score_kill": 1.0
        },
        "tco": {"max_total_cost_bps": 1.0, "max_impact_bps": 1.0},
        "storage": {"run_dir": str(tmp_path / "runs")},
        "fixtures": {"ohlcv_csv": "data/fixtures/perps/btcusdt_perp_5m.csv"}
    }
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    out = run_replay(str(p), source="recordings", run_id="r1")
    assert out["events"] > 0
