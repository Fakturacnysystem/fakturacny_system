from datetime import datetime, timezone, timedelta

import pytest

from autonomous_investment_robot.services.feature_store.service import FeatureStoreService


def test_feature_leakage_prevention():
    svc = FeatureStoreService()
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        svc.assert_no_leakage(now + timedelta(minutes=1), now)


def test_feature_build_contains_version():
    svc = FeatureStoreService(feature_version="vtest")
    fv = svc.build("BTCUSDT", datetime.now(timezone.utc), {"ret_5m": 0.1})
    assert fv.feature_version == "vtest"
