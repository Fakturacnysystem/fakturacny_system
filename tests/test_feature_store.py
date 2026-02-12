from datetime import datetime, timedelta, timezone

import pytest

from autonomous_investment_robot.services.data_ingestion.service import IngestedBar
from autonomous_investment_robot.services.feature_store.service import FeatureStoreService


def test_feature_leakage_prevention():
    svc = FeatureStoreService()
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        svc.assert_no_leakage(now + timedelta(minutes=1), now)


def test_feature_build_is_deterministic_and_versioned():
    svc = FeatureStoreService(feature_version="vtest")
    bars = [
        IngestedBar("fixture", "BTCUSDT", datetime(2026, 1, 1, tzinfo=timezone.utc), 1, 2, 1, 1.5, 100),
        IngestedBar("fixture", "BTCUSDT", datetime(2026, 1, 1, 1, tzinfo=timezone.utc), 1.5, 2.5, 1.2, 2.0, 110),
    ]
    f1 = svc.build_from_bars(bars)
    f2 = svc.build_from_bars(bars)
    assert f1[1].feature_version == "vtest"
    assert f1[1].values == f2[1].values
