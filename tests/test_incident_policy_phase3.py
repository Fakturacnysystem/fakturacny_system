from autonomous_investment_robot.config.settings import RiskLimits
from autonomous_investment_robot.services.incident.service import IncidentAction, IncidentPolicy, IncidentResponder
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


def test_incident_policy_crowding_extreme_maps_to_kill():
    p = IncidentPolicy()
    inc = p.evaluate({"crowding_level": 4.0, "crowding_score": 30.0, "crowding_score_extreme": 25.0})
    assert inc is not None
    assert inc.reason == "CrowdingExtreme"


def test_incident_policy_funding_budget_warns_and_then_exits():
    p = IncidentPolicy()
    inc1 = p.evaluate({"funding_budget_utilization": 0.85})
    assert inc1 is not None
    assert inc1.reason == "FundingBudgetHigh"
    inc2 = p.evaluate({"funding_budget_utilization": 1.05})
    assert inc2 is not None
    assert inc2.reason == "FundingBudgetExceeded"


def test_incident_responder_sets_kill_safe_flatten_cooldown_on_risk_engine():
    risk = RiskEngineService(
        limits=RiskLimits(
            max_daily_loss_pct=5.0,
            max_drawdown_pct=10.0,
            max_position_notional=1000.0,
            max_exposure_notional=2000.0,
            max_orders_per_min=10,
            leverage=0,
            max_spread_bps=20.0,
            min_depth_notional=100.0,
            stale_data_seconds=60.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=3.0,
            max_liquidation_spike=100000.0,
            divergence_threshold_bps=30.0,
            crowding_score_kill=25.0,
        ),
        safe_mode=False,
    )
    out = IncidentResponder().execute(IncidentAction("kill_flatten_cooldown", "Chaos"), risk_engine=risk)
    assert out.kill is True
    assert out.safe_mode is True
    assert out.flatten_requested is True
    assert out.cooldown_applied is True
    assert risk.state.kill_switch is True
    assert risk.state.safe_mode is True
