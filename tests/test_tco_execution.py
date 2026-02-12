from autonomous_investment_robot.services.execution.tco import anti_toxic_block, slice_notional
from autonomous_investment_robot.services.policy.tco import estimate_cost, estimate_edge, should_trade


def test_cost_optimizer_veto_math():
    cost = estimate_cost(fee_bps=2, slippage_bps=2, funding_bps=1, spread_bps=10, impact_bps=3, maker=True)
    edge = estimate_edge(forecast_mu=0.0002, confidence=0.5)
    assert should_trade(edge, cost, safety_buffer_bps=2.0, min_confidence=0.5, confidence=0.5) is False


def test_execution_slicing_deterministic():
    s = slice_notional(1200, slicing_parts=3, max_participation_rate=0.1, depth_notional=10000)
    assert s == [333.3333333333333, 333.3333333333333, 333.3333333333333]


def test_anti_toxic_filter_blocks():
    assert anti_toxic_block(3.0, 150000, 0.0006, 30) is True
