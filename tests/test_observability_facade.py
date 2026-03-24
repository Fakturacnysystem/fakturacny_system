from datetime import datetime, timezone
from pathlib import Path

from autonomous_investment_robot.services.observability_facade.service import ObservabilityFacade
from autonomous_investment_robot.services.observability_service.service import ObservabilityService
from autonomous_investment_robot.services.ops.service import OpsService


def test_observability_facade_routes_dedicated_channels(tmp_path):
    facade = ObservabilityFacade(ObservabilityService(str(tmp_path), OpsService(str(tmp_path))))

    facade.route_spre({"symbol": "BTCUSDT", "ts": datetime.now(timezone.utc), "dominant_action": "no_trade"})
    facade.route_shadow({"symbol": "BTCUSDT", "ts": datetime.now(timezone.utc), "action": "wait"})
    facade.route_mastermind({"symbol": "BTCUSDT", "ts": datetime.now(timezone.utc), "decision": "PROBE"})
    facade.route_decision_doctrine({"symbol": "BTCUSDT", "ts": datetime.now(timezone.utc), "recommended_action": "trade_smaller"})
    facade.route_execution_simulation({"symbol": "BTCUSDT", "ts": datetime.now(timezone.utc), "recommended_action": "trade_smaller"})
    facade.route_escalation({"symbol": "BTCUSDT", "ts": datetime.now(timezone.utc), "action": "manual_review"})
    facade.route_truth_evidence("provider_capability_journal", {"provider_id": "binance_um_perps"})

    assert Path(tmp_path / "spre_journal.jsonl").exists()
    assert Path(tmp_path / "shadow_rival_journal.jsonl").exists()
    assert Path(tmp_path / "mastermind_journal.jsonl").exists()
    assert Path(tmp_path / "decision_doctrine_journal.jsonl").exists()
    assert Path(tmp_path / "execution_simulation_journal.jsonl").exists()
    assert Path(tmp_path / "human_escalation_journal.jsonl").exists()
    assert Path(tmp_path / "provider_capability_journal.jsonl").exists()
    route_index = tmp_path / "observability_route_index.jsonl"
    assert route_index.exists()
    content = route_index.read_text(encoding="utf-8")
    assert "spre_journal" in content
    assert "shadow_rival_journal" in content
    assert "mastermind_journal" in content
    assert "decision_doctrine_journal" in content
