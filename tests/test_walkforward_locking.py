from autonomous_investment_robot.services.data_ingestion.service import DataIngestionService
from autonomous_investment_robot.services.feature_store.service import FeatureStoreService


def test_infoset_locking_on_fixture_walk():
    ing = DataIngestionService()
    bars = ing.replay_csv("BTCUSDT", "data/fixtures/btcusdt_1h.csv")
    fs = FeatureStoreService()
    fvs = fs.build_from_bars(bars)
    for i in range(1, len(fvs)):
        fs.assert_no_leakage(fvs[i - 1].ts, bars[i].ts)
