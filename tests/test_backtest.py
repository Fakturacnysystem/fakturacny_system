from autonomous_investment_robot.backtest.harness import simulate_backtest
from autonomous_investment_robot.backtest.stress import run_paper_chaos_suite, summarize_chaos_suite
from autonomous_investment_robot.backtest.walk_forward import walk_forward_splits
from autonomous_investment_robot.config.settings import ExecutionSettings, RiskLimits
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.risk_engine.service import RiskEngineService


def test_backtest_and_walk_forward():
    prices = [100, 101, 102, 100, 99, 101, 103, 102, 104, 105]
    bt = simulate_backtest(prices)
    assert "equity" in bt[0]
    splits = walk_forward_splits(bt, train=4, test=2)
    assert len(splits) > 0


def test_deterministic_chaos_suite_ends_fail_closed_flatten():
    risk = RiskEngineService(
        limits=RiskLimits(
            max_daily_loss_pct=5.0,
            max_weekly_loss_pct=10.0,
            max_drawdown_pct=10.0,
            max_position_notional=1000.0,
            max_exposure_notional=5000.0,
            max_symbol_exposure_notional=2500.0,
            max_cluster_exposure_notional=4000.0,
            max_orders_per_min=10,
            leverage=0,
            cvar_limit_pct=10.0,
            stress_loss_limit_pct=50.0,
            max_spread_bps=20.0,
            min_depth_notional=100.0,
            stale_data_seconds=60.0,
            min_margin_buffer=2.0,
            max_funding_cost_per_day=1.0,
            max_oi_spike_pct=3.0,
            max_liquidation_spike=100000.0,
            divergence_threshold_bps=30.0,
            crowding_score_kill=25.0,
            crowding_score_medium=10.0,
            crowding_score_high=18.0,
            crowding_score_extreme=25.0,
        ),
        safe_mode=False,
    )
    exe = ExecutionService(ExecutionSettings())
    intent = OrderIntent(symbol="BTCUSDT", side="buy", target_notional=100.0, why={})
    summary = summarize_chaos_suite(run_paper_chaos_suite(risk, exe, intent))
    assert summary["count"] == 5
    assert summary["passed"] is True
