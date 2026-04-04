from __future__ import annotations

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.autonomous_decision.service import AutonomousDecisionService


def test_opportunity_engine_selects_best_live_candidate_and_tracks_rejections() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    service = AutonomousDecisionService(settings)

    bundle = service.evaluate(
        candidates=[
            {
                "symbol": "SOL/EUR",
                "playbook": "trend_follow_entry",
                "side": "buy",
                "expected_net_edge_bps": 22.0,
                "confidence": 0.8,
                "quality_of_edge": 0.75,
                "capital_efficiency": 0.7,
                "opportunity_decay": 0.9,
                "target_notional": 10.0,
                "live_enabled": True,
            },
            {
                "symbol": "BTC/EUR",
                "playbook": "mean_reversion_entry",
                "side": "buy",
                "expected_net_edge_bps": 8.0,
                "confidence": 0.55,
                "quality_of_edge": 0.45,
                "capital_efficiency": 0.5,
                "opportunity_decay": 0.7,
                "target_notional": 999.0,
                "live_enabled": True,
            },
            {
                "symbol": "ETH/EUR",
                "playbook": "volatility_expansion",
                "side": "buy",
                "expected_net_edge_bps": 15.0,
                "confidence": 0.7,
                "quality_of_edge": 0.65,
                "capital_efficiency": 0.6,
                "opportunity_decay": 0.8,
                "target_notional": 12.0,
                "live_enabled": False,
            },
        ],
        capital_envelope={"playbook_level_cap": 25.0},
        expectancy={"net_expectancy_bps": 11.0},
        runtime_ordering_allowed=True,
    )

    assert bundle["selected_candidate"]["symbol"] == "SOL/EUR"
    assert bundle["decision_ranking_explainability"]["selected_playbook"] == "trend_follow_entry"
    assert bundle["opportunity_backlog_report"]["candidate_count"] == 3
    assert bundle["candidate_rejection_matrix"]["BTC/EUR:mean_reversion_entry"] == ["playbook_cap_exceeded"]
    assert "signal_crowding_score" in bundle["signal_crowding_report"]
