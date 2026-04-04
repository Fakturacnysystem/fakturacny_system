from __future__ import annotations

from types import SimpleNamespace

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.policy.playbooks.service import PlaybookFrameworkService


def test_playbook_framework_emits_live_and_shadow_candidates_with_reason_codes() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    settings.playbooks.shadow_only_playbooks = ["inventory_unwind"]
    service = PlaybookFrameworkService(settings)

    bundle = service.evaluate(
        symbol="SOL/EUR",
        forecast=SimpleNamespace(mu=0.0018, sigma=0.002, confidence=0.83, regime="strong_trend"),
        regime_assessment=SimpleNamespace(label="strong_trend"),
        features={"spread_proxy": 0.0002, "seconds_since_distinct_book_change": 2.0},
        execution_quality=SimpleNamespace(adverse_selection_risk=0.1),
        inventory_state=SimpleNamespace(stale_inventory_score=0.1),
        expectancy_report={"net_expectancy_bps": 12.0, "avg_win_bps": 18.0, "metadata": {"confidence_calibration": 0.72}},
    )

    candidates = bundle["candidates"]
    assert candidates[0]["playbook"] == "trend_follow_entry"
    assert any(candidate["playbook"] == "inventory_unwind" and candidate["live_enabled"] is False for candidate in candidates)
    assert any(candidate["expected_net_edge_bps"] > 0.0 for candidate in candidates)
    assert bundle["playbook_disable_reasons"]["disable_reasons"]
