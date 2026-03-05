from datetime import datetime, timezone
import json

from autonomous_investment_robot.services.data_ingestion.multi_venue_engine import MultiVenueMarketDataEngine, VenueQuote
from autonomous_investment_robot.services.research.service import ResearchPlatformService


def test_market_data_engine_selects_fallback_and_writes_tick(tmp_path):
    svc = MultiVenueMarketDataEngine(str(tmp_path), stale_after_s=1.0, max_clock_drift_ms=200.0)
    now_ts = 1_700_000_000.0
    svc.update_clock_drift("primary", venue_ts_ms=now_ts * 1000.0 + 500.0, now_ts=now_ts)
    q_primary = VenueQuote("primary", "XBTEUR", bid=100.0, ask=101.0, depth_notional=10_000.0, ts=now_ts - 5.0)
    q_fallback = VenueQuote("fallback", "XBTEUR", bid=100.1, ask=100.2, depth_notional=50_000.0, ts=now_ts, source="rest_fallback")
    best, quality, used_fallback = svc.choose_with_fallback("primary", [q_primary, q_fallback], now_ts=now_ts, min_primary_score=30.0)
    assert best is not None
    assert used_fallback is True
    q = quality[best.venue]
    svc.append_tick(best, q)
    tick_file = tmp_path / "ticks" / "xbteur.jsonl"
    assert tick_file.exists()
    rows = [json.loads(line) for line in tick_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1


def test_research_platform_parity_and_nested_walk_forward(tmp_path):
    svc = ResearchPlatformService(str(tmp_path))
    reg = svc.register_feature_schema("v1", ["ret_1", "ret_3"])
    assert reg.feature_version == "v1"

    ok, issues = svc.assert_online_offline_parity("v1", {"ret_1": 1.0, "ret_3": 2.0}, {"ret_1": 1.0, "ret_3": 2.0})
    assert ok is True
    assert issues == []

    leak_ok, leak_reason = svc.leakage_test(datetime.now(timezone.utc), datetime.now(timezone.utc))
    assert leak_ok is True
    assert leak_reason == "ok"

    prices = [100.0 + i * 0.1 for i in range(200)]
    nested = svc.nested_walk_forward(prices)
    gate = svc.robust_oos_gate(nested)
    assert "outer_splits" in nested
    assert "allowed" in gate
