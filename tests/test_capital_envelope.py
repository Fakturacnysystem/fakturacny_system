from __future__ import annotations

from types import SimpleNamespace

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.capital_envelope.service import CapitalEnvelopeService


def test_capital_envelope_report_derives_heat_efficiency_and_dead_capital() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    service = CapitalEnvelopeService(settings)

    reserve_state = SimpleNamespace(
        total_capital=500.0,
        quote_free_balance=320.0,
        reserve_floor_quote=150.0,
        reasons=["reserve_floor_binding"],
    )
    inventory_state = SimpleNamespace(
        gross_open_notional=60.0,
        weighted_age_seconds=90.0 * 60.0,
        stale_inventory_score=0.35,
    )
    execution_plan = SimpleNamespace(target_notional=25.0)
    execution_result = SimpleNamespace(status="accepted")

    bundle = service.summarize(
        reserve_state=reserve_state,
        inventory_state=inventory_state,
        execution_plan=execution_plan,
        execution_result=execution_result,
    )

    summary = bundle["capital_envelope_summary"]
    assert summary["total_equity"] == 500.0
    assert summary["live_deployment_cap"] > 0.0
    assert bundle["capital_utilization_diagnostics"]["capital_utilization_pct"] > 0.0
    assert 0.0 <= summary["capital_efficiency_score"] <= 1.0
    assert 0.0 <= summary["dead_capital_pressure"] <= 1.0
    assert bundle["deployment_efficiency_report"]["pair_level_cap"] <= settings.capital_envelope.max_pair_exposure_notional
