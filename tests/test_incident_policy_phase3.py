from autonomous_investment_robot.services.incident.service import IncidentPolicy


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
