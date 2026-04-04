from __future__ import annotations

from types import SimpleNamespace

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.capital_envelope.service import CapitalEnvelopeService


def test_dead_capital_metrics_raise_pressure_when_idle_capital_and_inventory_age_are_high() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    settings.capital_envelope.max_capital_lock_time_min = 30.0
    service = CapitalEnvelopeService(settings)

    bundle = service.summarize(
        reserve_state=SimpleNamespace(total_capital=300.0, quote_free_balance=280.0, reserve_floor_quote=30.0, reasons=[]),
        inventory_state=SimpleNamespace(gross_open_notional=5.0, weighted_age_seconds=120.0 * 60.0, stale_inventory_score=0.8),
        execution_plan=SimpleNamespace(target_notional=0.0),
    )

    report = bundle["dead_capital_pressure_report"]
    assert report["dead_capital_pressure"] > 0.5
    assert report["weighted_age_minutes"] == 120.0
    assert bundle["capital_utilization_report"]["idle_capital"] > 0.0
