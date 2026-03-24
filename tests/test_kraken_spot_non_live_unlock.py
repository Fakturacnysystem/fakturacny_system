from __future__ import annotations

import csv
import json
from pathlib import Path

from autonomous_investment_robot.main import run_replay_report, run_with_config


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_fixture_csv(path: Path) -> None:
    rows = [
        {
            "ts": "2026-01-01T00:00:00Z",
            "open": 100.0,
            "high": 101.0,
            "low": 99.5,
            "close": 100.5,
            "volume": 10.0,
            "mark_price": 100.5,
            "index_price": 100.5,
            "funding_rate": 0.0,
            "oi": 0.0,
            "liquidations": 0.0,
            "depth_notional": 50000.0,
            "spread_bps": 4.0,
            "secondary_price": 100.5,
        },
        {
            "ts": "2026-01-01T01:00:00Z",
            "open": 100.5,
            "high": 101.8,
            "low": 100.0,
            "close": 101.2,
            "volume": 12.0,
            "mark_price": 101.2,
            "index_price": 101.2,
            "funding_rate": 0.0,
            "oi": 0.0,
            "liquidations": 0.0,
            "depth_notional": 52000.0,
            "spread_bps": 5.0,
            "secondary_price": 101.2,
        },
        {
            "ts": "2026-01-01T02:00:00Z",
            "open": 101.2,
            "high": 102.0,
            "low": 100.9,
            "close": 101.7,
            "volume": 15.0,
            "mark_price": 101.7,
            "index_price": 101.7,
            "funding_rate": 0.0,
            "oi": 0.0,
            "liquidations": 0.0,
            "depth_notional": 54000.0,
            "spread_bps": 4.0,
            "secondary_price": 101.7,
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _load_config(name: str) -> dict:
    return json.loads((REPO_ROOT / name).read_text(encoding="utf-8"))


def _write_config(tmp_path: Path, name: str, *, run_dir: Path, fixture_csv: Path, extra: dict | None = None) -> Path:
    payload = _load_config(name)
    payload.setdefault("storage", {})["run_dir"] = str(run_dir)
    payload.setdefault("fixtures", {})["ohlcv_csv"] = str(fixture_csv)
    if extra:
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(payload.get(key), dict):
                payload[key].update(value)
            else:
                payload[key] = value
    cfg = tmp_path / name
    cfg.write_text(json.dumps(payload), encoding="utf-8")
    return cfg


def test_kraken_spot_paper_full_analysis_emits_bundles_and_journals(tmp_path: Path) -> None:
    fixture_csv = tmp_path / "spot.csv"
    _write_fixture_csv(fixture_csv)
    run_dir = tmp_path / "paper_full_analysis"
    cfg = _write_config(tmp_path, "config.kraken_spot.paper_full_analysis.yaml", run_dir=run_dir, fixture_csv=fixture_csv)

    result = run_with_config(str(cfg))

    assert result["status"] == "ok"
    assert (run_dir / "harmony_report.json").exists()
    assert (run_dir / "harmony_boot_report.json").exists()
    assert (run_dir / "signal_interference_journal.jsonl").exists()
    assert (run_dir / "provider_capability_journal.jsonl").exists()
    assert (run_dir / "market_integrity_journal.jsonl").exists()
    assert (run_dir / "market_watch_journal.jsonl").exists()
    assert (run_dir / "kraken_spot_replay_summary.json").exists()
    assert (run_dir / "kraken_spot_operator_summary.json").exists()
    assert (run_dir / "activated_capabilities.json").exists()
    assert (run_dir / "still_gated_capabilities.json").exists()
    assert (run_dir / "doctrine_blocked_capabilities.json").exists()
    assert (run_dir / "kraken_spot_capability_unlock_matrix.json").exists()
    operator_summary = json.loads((run_dir / "kraken_spot_operator_summary.json").read_text(encoding="utf-8"))
    assert operator_summary["event_status"]["partial"] is True


def test_kraken_spot_paper_full_analysis_event_fixture_removes_partial_event_status(tmp_path: Path) -> None:
    fixture_csv = tmp_path / "spot.csv"
    _write_fixture_csv(fixture_csv)
    events = [
        {
            "ts": "2026-01-01T00:30:00+00:00",
            "source": "wire",
            "trust_score": 0.9,
            "novelty": 0.8,
            "relevance": 0.9,
            "symbols": ["BTC/USD"],
            "impact_score": 0.7,
            "sentiment": 0.5,
            "manipulation_risk": 0.1,
        }
    ]
    event_fixture = tmp_path / "events.json"
    event_fixture.write_text(json.dumps(events), encoding="utf-8")
    run_dir = tmp_path / "paper_events"
    cfg = _write_config(
        tmp_path,
        "config.kraken_spot.paper_full_analysis.yaml",
        run_dir=run_dir,
        fixture_csv=fixture_csv,
        extra={"kraken_spot_non_live": {"event_fixture_path": str(event_fixture)}},
    )

    result = run_with_config(str(cfg))

    assert result["status"] == "ok"
    operator_summary = json.loads((run_dir / "kraken_spot_operator_summary.json").read_text(encoding="utf-8"))
    activated = json.loads((run_dir / "activated_capabilities.json").read_text(encoding="utf-8"))
    assert operator_summary["event_status"]["partial"] is False
    assert activated["EventIntelligenceService"]["activation_state"] == "active"


def test_kraken_spot_replay_full_analysis_uses_recordings(tmp_path: Path) -> None:
    fixture_csv = tmp_path / "spot.csv"
    _write_fixture_csv(fixture_csv)
    run_dir = tmp_path / "replay_full_analysis"
    recording_dir = run_dir / "recordings" / "session-1"
    recording_dir.mkdir(parents=True)
    market_lines = [
        '{"stream":"btcusd@aggTrade","data":{"e":"aggTrade","s":"BTC/USD","a":1,"E":1767225600000,"T":1767225600000,"p":"100.5","q":"0.1","m":false}}',
        '{"stream":"btcusd@aggTrade","data":{"e":"aggTrade","s":"BTC/USD","a":2,"E":1767229200000,"T":1767229200000,"p":"101.0","q":"0.2","m":false}}',
        '{"stream":"btcusd@aggTrade","data":{"e":"aggTrade","s":"BTC/USD","a":3,"E":1767232800000,"T":1767232800000,"p":"101.5","q":"0.2","m":false}}',
    ]
    (recording_dir / "market.jsonl").write_text("\n".join(market_lines) + "\n", encoding="utf-8")
    (recording_dir / "market.index.json").write_text(json.dumps({"events": 3, "schema_version": 1}), encoding="utf-8")
    (recording_dir / "market.meta.json").write_text(json.dumps({"schema_version": 1, "format": "jsonl"}), encoding="utf-8")
    cfg = _write_config(tmp_path, "config.kraken_spot.replay_full_analysis.yaml", run_dir=run_dir, fixture_csv=fixture_csv)

    result = run_replay_report(str(cfg))

    assert result["status"] == "ok"
    assert (run_dir / "kraken_spot_replay_summary.json").exists()
    replay_summary = json.loads((run_dir / "kraken_spot_replay_summary.json").read_text(encoding="utf-8"))
    assert replay_summary["input_source"] == "recordings"


def test_kraken_spot_readonly_analysis_emits_bundle_without_ordering(monkeypatch, tmp_path: Path) -> None:
    from autonomous_investment_robot.core import orchestrator as orchestrator_module

    class FakeReadonlyConnector:
        provider_id = "kraken_spot"
        supports_live_trading = True

        @property
        def has_credentials(self) -> bool:
            return False

        def book_ticker(self, symbol):  # noqa: ARG002
            return {
                "symbol": "BTC/USD",
                "bidPrice": "100.0",
                "askPrice": "100.1",
                "bidQty": "2.0",
                "askQty": "2.0",
                "timestamp": 1_700_000_000_000,
            }

    monkeypatch.setattr(orchestrator_module, "KrakenSpotConnector", lambda settings: FakeReadonlyConnector())
    fixture_csv = tmp_path / "spot.csv"
    _write_fixture_csv(fixture_csv)
    run_dir = tmp_path / "readonly_analysis"
    cfg = _write_config(tmp_path, "config.kraken_spot.readonly_analysis.yaml", run_dir=run_dir, fixture_csv=fixture_csv)

    result = run_with_config(str(cfg))

    assert result["status"] == "ok"
    assert result["mode"] == "live_readonly"
    assert result["reason"] == "live_preflight_passed"
    assert (run_dir / "kraken_spot_operator_summary.json").exists()
    assert (run_dir / "kraken_spot_replay_summary.json").exists()
