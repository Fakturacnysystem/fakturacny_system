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
