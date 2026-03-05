from autonomous_investment_robot.backtest.harness import run_walk_forward_oos, simulate_backtest
from autonomous_investment_robot.backtest.stress import run_paper_chaos_suite, summarize_chaos_suite
from autonomous_investment_robot.backtest.walk_forward import (
    evaluate_window,
    overfit_penalty,
    summarize_walk_forward_oos,
    walk_forward_oos,
    walk_forward_quality_gate,
    walk_forward_splits,
)
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
    oos = walk_forward_oos(bt, train=4, test=2)
    assert len(oos) == len(splits)
    assert "oos_metrics" in oos[0]
    summary = summarize_walk_forward_oos(oos)
    assert summary["splits"] == float(len(oos))
    assert "avg_oos_sharpe" in summary


def test_walk_forward_harness_returns_oos_summary():
    prices = [100, 99, 101, 103, 104, 102, 101, 100, 102, 105, 104, 106]
    out = run_walk_forward_oos(prices, train=4, test=2)
    assert "splits" in out
    assert "summary" in out
    assert "penalty" in out
    assert "gate" in out
    assert out["summary"]["splits"] >= 1.0


def test_evaluate_window_reports_core_metrics():
    rows = simulate_backtest([100, 102, 101, 103, 105])
    metrics = evaluate_window(rows)
    assert metrics["trades"] == float(len(rows))
    assert "sharpe" in metrics
    assert "sortino" in metrics
    assert "max_drawdown" in metrics


def test_overfit_penalty_and_quality_gate():
    rows = simulate_backtest([100, 101, 102, 98, 99, 100, 101, 102, 103, 104, 103, 105, 106, 107, 108])
    splits = walk_forward_oos(rows, train=6, test=3)
    pen = overfit_penalty(splits)
    summary = summarize_walk_forward_oos(splits)
    gate = walk_forward_quality_gate(summary, pen)
    assert "pbo" in pen
    assert "deflated_sharpe" in pen
    assert gate["reason"] in {
        "walk_forward_pass",
        "oos_return_too_low",
        "deflated_sharpe_too_low",
        "pbo_too_high",
        "regime_stability_too_low",
    }


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
