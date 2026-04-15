from __future__ import annotations

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.portfolio_allocator.service import PortfolioAllocatorService


def test_portfolio_allocator_enters_recovery_mode_and_sizes_down() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    service = PortfolioAllocatorService(settings)

    bundle = service.allocate(
        capital_envelope={
            "pair_level_cap": 80.0,
            "playbook_level_cap": 40.0,
            "regime_level_cap": 35.0,
            "dead_capital_pressure": 0.65,
        },
        expectancy={
            "net_expectancy_bps": -3.0,
            "false_positive_rate": 0.3,
        },
        selected_candidate={
            "symbol": "SOL/EUR",
            "playbook": "trend_follow_entry",
            "target_notional": 30.0,
            "confidence": 0.61,
            "quality_of_edge": 0.56,
        },
    )

    assert bundle["allocator_decisions"]["recovery_mode"] is True
    assert bundle["allocator_decisions"]["recommended_notional"] <= 30.0
    assert bundle["recovery_mode_report"]["recovery_mode"] is True
    assert bundle["confidence_bucket_exposure"]["confidence_bucket"] == "medium"
