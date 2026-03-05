from __future__ import annotations

from pathlib import Path

import pandas as pd

from autonomous_investment_robot.backtest.portfolio_engine import export_portfolio_report, run_portfolio_backtest


def test_portfolio_backtest_multi_symbol_and_report(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {"symbol": "XBTUSD", "timestamp": 1, "price": 100.0},
            {"symbol": "XBTUSD", "timestamp": 2, "price": 101.0},
            {"symbol": "ETHEUR", "timestamp": 1, "price": 200.0},
            {"symbol": "ETHEUR", "timestamp": 2, "price": 202.0},
        ]
    )
    rep = run_portfolio_backtest(df, fee_bps=2.0, slippage_bps=3.0, funding_bps=1.0, profit_target_net=0.02)
    assert rep.summary["symbols"] == 2
    files = export_portfolio_report(rep, output_dir=str(tmp_path))
    assert Path(files["csv"]).exists()
    assert Path(files["md"]).exists()
