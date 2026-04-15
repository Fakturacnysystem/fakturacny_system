from __future__ import annotations

from autonomous_investment_robot.config.settings import RobotSettings
from autonomous_investment_robot.services.universe.service import MarketUniverseService


def test_market_universe_ranks_active_pair_and_clusters_candidates() -> None:
    settings = RobotSettings.from_file("config.kraken_spot.paper.yaml")
    settings.market_universe.pair_universe = ["SOL/EUR", "BTC/EUR", "ETH/EUR"]
    settings.market_universe.max_active_pairs = 2
    service = MarketUniverseService(settings)

    bundle = service.evaluate(
        symbol="SOL/EUR",
            microstructure={
                "spread_bps": 4.0,
                "depth_notional": 30_000.0,
                "realized_volatility": 0.18,
                "microstructure_quality_score": 0.74,
                "stale_book_seconds": 1.5,
            },
        expectancy={
            "net_expectancy_bps": 18.0,
            "metadata": {"fill_rate": 0.72},
        },
        capital_envelope={
            "pair_level_cap": 75.0,
            "capital_efficiency_score": 0.68,
        },
        regime_label="strong_trend",
    )

    ranking = bundle["pair_ranking_report"]
    assert ranking["active_symbols"][0] == "SOL/EUR"
    assert len(ranking["ranked_pairs"]) == 3
    assert bundle["pair_cluster_report"]["clusters"]
    assert "SOL/EUR" in bundle["pair_admission_expulsion_report"]["admitted"]
