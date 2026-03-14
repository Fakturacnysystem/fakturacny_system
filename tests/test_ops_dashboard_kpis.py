import json
from pathlib import Path

from autonomous_investment_robot.services.ops.service import OpsService


def test_dashboard_snapshot_contains_execution_and_performance_kpis(tmp_path):
    ops = OpsService(str(tmp_path))
    ops.set_metric("net_pnl_after_fees", 12.3)
    ops.set_metric("fill_rate", 0.8)
    ops.set_metric("reject_rate", 0.2)
    ops.set_metric("slippage_vs_model_bps", 1.1)
    ops.set_metric("max_drawdown", 3.2)
    ops.set_metric("sharpe", 1.5)
    ops.set_metric("sortino", 2.0)
    ops.set_metric("implementation_shortfall_bps", 0.8)
    ops.set_metric("latency_p95_ms", 320.0)
    ops.set_metric("fill_probability", 0.55)
    ops.set_metric("world_state_available", 1.0)
    ops.set_metric("world_state_graph_available", 1.0)
    ops.set_metric("world_state_safe_to_trade", 1.0)
    ops.set_metric("world_state_stale_domains_count", 0.0)
    ops.set_metric("world_state_stale_critical_domains_count", 0.0)
    ops.set_metric("world_state_freshness_max_s", 1.2)
    ops.set_metric("world_state_market_stale_s", 0.6)
    snapshot = Path(ops.export_dashboard_snapshot())
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert "execution" in payload["groups"]
    assert "performance" in payload["groups"]
    assert "execution_qa" in payload["groups"]
    assert "attribution" in payload["groups"]
    assert "model_ops" in payload["groups"]
    assert "market_data" in payload["groups"]
    assert "treasury" in payload["groups"]
    assert "governance" in payload["groups"]
    assert "reliability" in payload["groups"]
    assert "efficiency" in payload["groups"]
    assert "world_state" in payload["groups"]
    assert payload["groups"]["execution"]["fill_rate"] == 0.8
    assert payload["groups"]["performance"]["net_pnl_after_fees"] == 12.3
    assert payload["groups"]["execution_qa"]["fill_probability"] == 0.55
    assert payload["groups"]["world_state"]["world_state_freshness_max_s"] == 1.2
