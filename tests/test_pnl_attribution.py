from __future__ import annotations

import json
from pathlib import Path

from autonomous_investment_robot.services.execution.cost_engine import CostEngineService
from autonomous_investment_robot.services.ops.service import OpsService


def test_cost_engine_implementation_shortfall_sign_and_ratio():
    engine = CostEngineService()
    buy_shortfall = engine.implementation_shortfall_bps(side="buy", arrival_price=100.0, fill_price=100.2)
    sell_shortfall = engine.implementation_shortfall_bps(side="sell", arrival_price=100.0, fill_price=99.8)

    assert buy_shortfall > 0.0
    assert sell_shortfall > 0.0

    ratio = engine.cost_to_alpha_ratio(alpha_bps=3.0, cost_bps=1.5)
    assert ratio == 0.5

    est = engine.estimate(
        notional=100.0,
        depth_notional=20_000.0,
        spread_bps=4.0,
        fee_bps=10.0,
        slippage_bps=3.0,
        maker=True,
    )
    assert est.total_bps > 0.0


def test_dashboard_keeps_null_slippage_when_no_fills(tmp_path):
    ops = OpsService(str(tmp_path))
    ops.set_metric("intents_total", 4.0)
    ops.set_metric("executions_submitted_total", 2.0)
    ops.set_metric("fills_confirmed_total", 0.0)
    ops.set_metric("slippage_vs_model_bps", None)
    ops.set_metric("execution_shortfall_bps", 1.2)
    ops.set_metric("cost_to_alpha_ratio_modeled", 0.85)
    snapshot = Path(ops.export_dashboard_snapshot())
    payload = json.loads(snapshot.read_text(encoding="utf-8"))

    assert payload["groups"]["execution"]["slippage_vs_model_bps"] is None
    assert payload["groups"]["efficiency"]["execution_shortfall_bps"] == 1.2
    assert payload["groups"]["efficiency"]["cost_to_alpha_ratio_modeled"] == 0.85

