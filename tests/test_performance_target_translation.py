from __future__ import annotations

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.performance_target_translation.service import (
    PerformanceTargetTranslationService,
)


def test_performance_target_translation_surfaces_implausibility_and_gaps() -> None:
    settings = RobotSettings.from_file("config.perps_intraday.paper.yaml")
    settings.performance_targets.monthly_return_pct = 30.0
    settings.performance_targets.round_trips_per_day = 1.0
    settings.performance_targets.capital_utilization_pct = 70.0
    service = PerformanceTargetTranslationService(settings)

    translation, gap = service.translate(
        capital_envelope={
            "total_equity": 500.0,
            "live_deployment_cap": 125.0,
        },
        expectancy={
            "net_expectancy_bps": 12.0,
            "metadata": {
                "fill_rate": 0.42,
                "maker_ratio": 0.55,
                "round_trips_per_day": 0.5,
            },
        },
        throughput={"fills": 0},
    )

    assert translation["required_daily_return_pct"] == 1.0
    assert translation["required_net_bps_per_trade"] > 100.0
    assert translation["theoretically_implausible"] is True
    assert gap["theoretically_implausible_under_current_capital_envelope"] is True
    assert gap["gaps"]["capital_utilization_gap_pct"] > 0.0
    assert gap["edge_shortfall_explanation"] in {
        "net_edge_shortfall",
        "utilization_shortfall",
        "turnover_shortfall",
        "fill_quality_shortfall",
    }
