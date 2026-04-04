from __future__ import annotations

from types import SimpleNamespace

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.exit_intelligence.service import ExitIntelligenceService


def test_exit_intelligence_keeps_cleanup_shadow_only_and_reason_coded() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    service = ExitIntelligenceService(settings)

    bundle = service.analyze(
        inventory_state=SimpleNamespace(
            stale_inventory_score=0.85,
            opportunity_cost_pressure=0.7,
            execution_fragility_pressure=0.4,
            weighted_age_seconds=300.0 * 60.0,
        ),
        profitability_context={"round_trip": {"action": "trade_smaller"}},
        market=SimpleNamespace(
            forecast=SimpleNamespace(mu=0.0006, sigma=0.004),
            regime_assessment=SimpleNamespace(label="strong_trend"),
        ),
        execution_result=SimpleNamespace(status="rejected"),
    )

    assert bundle["exit_decision_log"]["preferred_exit_family"] == "forced_inventory_cleanup_exit"
    assert bundle["exit_decision_log"]["metadata"]["shadow_only_cleanup_exit"] is True
    assert "inventory_pressure_high" in bundle["post_trade_root_cause_report"]["reasons"]
    assert bundle["inventory_pressure_report"]["inventory_pressure"] >= 0.7
