from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.data_qa.service import DataQAService


def test_divergence_breaker():
    bar = DataIngestionService().replay_csv("BTCUSDT", "data/fixtures/perps/btcusdt_perp_5m.csv")[9]
    qa = DataQAService()
    assert qa.divergence_breaker(bar, threshold_bps=10.0) is True


def test_schema_mismatch_fail_closed():
    qa = DataQAService()
    ok, reason = qa.schema_guard({"a": 1}, ["a", "b"])
    assert ok is False
    assert "schema_missing" in reason


def test_outlier_squash():
    qa = DataQAService()
    assert qa.outlier_squash(200.0, 0.0, 100.0) == 100.0


def test_ws_schema_guard_and_gap_detector():
    qa = DataQAService()
    ok, reason = qa.ws_schema_guard({"stream": "btcusdt@aggTrade", "data": {"e": "aggTrade", "s": "BTCUSDT"}})
    assert ok is True
    assert reason == "ok"
    ok2, reason2 = qa.ws_schema_guard({"data": {"e": "aggTrade"}})
    assert ok2 is False
    assert "schema_missing" in reason2

    gap, gr = qa.ws_gap_detector(100, 102)
    assert gap is True
    assert gr == "gap_detected"


def test_timestamp_sanity():
    qa = DataQAService()
    now_ms = 1_700_000_000_000
    ok, reason = qa.timestamp_sanity(now_ms - 1000, now_ms=now_ms)
    assert ok is True
    assert reason == "ok"
    ok2, reason2 = qa.timestamp_sanity(now_ms + 10_000, now_ms=now_ms)
    assert ok2 is False
    assert reason2 == "timestamp_in_future"
