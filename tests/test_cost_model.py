from __future__ import annotations

from types import SimpleNamespace

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.cost_model.service import FillAwareCostModelService


def test_cost_model_reports_fill_mix_and_degradation_bands() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    service = FillAwareCostModelService(settings)

    bundle = service.analyze(
        market=SimpleNamespace(book={"bid": 100.0, "ask": 100.1, "spread_bps": 10.0}),
        execution_plan=SimpleNamespace(order_style="limit"),
        execution_quality=SimpleNamespace(
            passive_preferred=True,
            expected_price_quality_bps=1.2,
            adverse_selection_risk=0.15,
            fill_probability=0.62,
        ),
        execution_result=SimpleNamespace(status="accepted"),
    )

    diagnostics = bundle["cost_model_diagnostics"]
    assert diagnostics["maker_probability"] > diagnostics["taker_probability"]
    assert diagnostics["total_cost_bps"] > float(settings.execution.fee_bps)
    assert bundle["cost_sensitivity_analysis"]["stress_bands"]["stress"] > diagnostics["total_cost_bps"]
    assert bundle["cancel_replace_efficiency"]["cancel_to_fill_ratio"] >= 0.0
