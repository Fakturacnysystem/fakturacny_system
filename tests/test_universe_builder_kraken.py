from autonomous_investment_robot.config.settings import UniverseBuilderSettings
from autonomous_investment_robot.services.policy.universe_builder import KrakenSpotUniverseBuilder


def test_universe_builder_watch_1000_caps_at_available():
    settings = UniverseBuilderSettings(top_n_target=1000, candidate_max=200, trade_max_positions=20)
    b = KrakenSpotUniverseBuilder(settings)
    pairs = {f"PAIR{i}": {"status": "tradable"} for i in range(150)}
    ticker = {f"PAIR{i}": {"b": ["99"], "a": ["101"], "v": ["0", str(1_000_000 - i)]} for i in range(150)}
    tiers = b.build(pairs, ticker)
    assert len(tiers.watch) == 150
    assert len(tiers.trade) <= 20
