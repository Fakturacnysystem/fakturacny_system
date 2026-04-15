from __future__ import annotations

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.experiments.service import ExperimentsService


def test_experiments_framework_surfaces_promotion_and_rollback_state() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    service = ExperimentsService(settings)

    bundle = service.evaluate(
        playbook_candidates=[
            {"playbook": "trend_follow_entry", "live_enabled": True},
            {"playbook": "mean_reversion_entry", "live_enabled": True},
            {"playbook": "inventory_unwind", "live_enabled": False},
        ],
        expectancy={
            "promotion_score": 0.42,
            "metadata": {"sample_guard": False},
        },
        health_summary={"blocking_reasons": ["readonly_mode"]},
    )

    assert bundle["experiment_registry"]["enabled"] is True
    assert bundle["rollback_trigger_report"]["rollback_triggered"] is True
    assert bundle["promotion_gate_report"]["eligible"] is False
    assert "inventory_unwind" in bundle["experiment_results_summary"]["shadow_variants"]
