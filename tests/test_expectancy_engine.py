from __future__ import annotations

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.expectancy_engine.service import ExpectancyEngineService


def test_expectancy_engine_computes_promotion_and_session_diagnostics() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    settings.expectancy.min_sample_guard = 3
    settings.expectancy.promotion_expectancy_bps = 12.0
    service = ExpectancyEngineService(settings)

    bundle = service.build(
        fills=[
            {"payload": {"fee": 0.1, "slippage_cost": 0.02}},
            {"payload": {"fee": 0.1, "slippage_cost": 0.01}},
            {"payload": {"fee": 0.08, "slippage_cost": 0.01}},
        ],
        order_events=[
            {"event_type": "ORDER_INTENT", "payload": {"metadata": {"execution_style": "maker_limit"}}},
            {"event_type": "ORDER_INTENT", "payload": {"metadata": {"execution_style": "maker_limit"}}},
            {"event_type": "ORDER_INTENT", "payload": {"metadata": {"execution_style": "taker_market"}}},
        ],
        trade_log=[
            {"net_bps": 18.0, "hold_minutes": 25.0},
            {"net_bps": 9.0, "hold_minutes": 30.0},
            {"net_bps": -4.0, "hold_minutes": 15.0},
        ],
        ranked_candidates=[
            {"playbook": "trend_follow_entry", "expected_net_edge_bps": 14.0, "admission_allowed": True},
            {"playbook": "mean_reversion_entry", "expected_net_edge_bps": 11.0, "admission_allowed": False},
        ],
    )

    report = bundle["expectancy_engine_report"]
    assert report["trade_count"] == 3
    assert report["net_expectancy_bps"] > 0.0
    assert 0.0 <= report["promotion_score"] <= 1.0
    assert bundle["playbook_promotion_readiness"]["trade_count"] == 3
    assert "asia" in bundle["intraday_session_model_report"]["sessions"]
    assert bundle["meta_router_report"]["best_playbook"] == "trend_follow_entry"
