from autonomous_investment_robot.services.execution.tco import anti_toxic_block, edge_after_cost, estimate_total_cost_bps, slice_notional


def test_cost_optimizer_veto_math():
    c = estimate_total_cost_bps(2, 2, 1, 10, maker=True)
    assert edge_after_cost(3, c) < 0


def test_execution_slicing_deterministic():
    s = slice_notional(1200, slicing_parts=3, max_participation_rate=0.1, depth_notional=10000)
    assert s == [333.3333333333333, 333.3333333333333, 333.3333333333333]


def test_anti_toxic_filter_blocks():
    assert anti_toxic_block(3.0, 150000, 0.0006, 30) is True
