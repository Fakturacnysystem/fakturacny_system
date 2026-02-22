from autonomous_investment_robot.main import run_with_config


def test_perps_intraday_paper_run_trades_and_metrics():
    result = run_with_config("config.perps_intraday.paper.yaml")
    assert result["status"] == "ok"
    assert result["orders"] >= 1
    assert result["fills"] >= 1
