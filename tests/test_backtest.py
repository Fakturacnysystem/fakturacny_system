from autonomous_investment_robot.backtest.harness import simulate_backtest
from autonomous_investment_robot.backtest.walk_forward import walk_forward_splits


def test_backtest_and_walk_forward():
    prices = [100, 101, 102, 100, 99, 101, 103, 102, 104, 105]
    bt = simulate_backtest(prices)
    assert "equity" in bt[0]
    splits = walk_forward_splits(bt, train=4, test=2)
    assert len(splits) > 0
