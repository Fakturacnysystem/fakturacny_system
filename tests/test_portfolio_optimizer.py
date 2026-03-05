from autonomous_investment_robot.services.portfolio.optimizer import PortfolioOptimizerService


def test_portfolio_optimizer_applies_cluster_caps_and_turnover_penalty():
    svc = PortfolioOptimizerService()
    candidates = {
        "XBTEUR": {
            "edge_bps": 12.0,
            "realized_vol": 0.008,
            "spread_bps": 2.0,
            "depth_notional": 1_200_000.0,
            "liquidity_score": 1.6,
            "cluster": "EUR",
        },
        "ETHEUR": {
            "edge_bps": 10.0,
            "realized_vol": 0.012,
            "spread_bps": 3.0,
            "depth_notional": 700_000.0,
            "liquidity_score": 1.2,
            "cluster": "EUR",
        },
        "SOLUSD": {
            "edge_bps": 11.0,
            "realized_vol": 0.016,
            "spread_bps": 5.0,
            "depth_notional": 900_000.0,
            "liquidity_score": 1.1,
            "cluster": "USD",
        },
    }
    corr = {
        "XBTEUR": {"XBTEUR": 1.0, "ETHEUR": 0.82, "SOLUSD": 0.25},
        "ETHEUR": {"XBTEUR": 0.82, "ETHEUR": 1.0, "SOLUSD": 0.3},
        "SOLUSD": {"XBTEUR": 0.25, "ETHEUR": 0.3, "SOLUSD": 1.0},
    }
    out = svc.optimize(
        candidates,
        corr=corr,
        current_weights={"XBTEUR": 0.7, "ETHEUR": 0.2, "SOLUSD": 0.1},
        turnover_penalty=0.2,
        cluster_caps={"EUR": 0.6, "USD": 0.7},
    )
    assert abs(sum(out.weights.values()) - 1.0) < 1e-6
    assert out.cluster_exposure["EUR"] <= 0.6001
    assert out.turnover >= 0.0
    assert out.score_by_symbol["XBTEUR"] > 0.0


def test_portfolio_optimizer_returns_zero_weights_when_no_edges():
    svc = PortfolioOptimizerService()
    out = svc.optimize(
        {
            "A": {"edge_bps": -1.0, "realized_vol": 0.01, "spread_bps": 20.0, "depth_notional": 10.0, "liquidity_score": 0.2},
            "B": {"edge_bps": 0.0, "realized_vol": 0.02, "spread_bps": 30.0, "depth_notional": 10.0, "liquidity_score": 0.2},
        }
    )
    assert out.weights == {"A": 0.0, "B": 0.0}
