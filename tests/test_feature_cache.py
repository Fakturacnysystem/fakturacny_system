from __future__ import annotations

import time

from autonomous_investment_robot.services.reliability.runtime_cache import FeatureCache


def test_feature_cache_hit_miss_and_expiry() -> None:
    cache = FeatureCache(ttl_s=0.05, max_items=4)
    assert cache.get("btc") is None
    cache.set("btc", {"ret_1": 0.01, "realized_vol": 0.002})
    got = cache.get("btc")
    assert got is not None
    assert got["ret_1"] == 0.01
    stats = cache.stats().to_dict()
    assert int(stats["hits"]) >= 1
    assert int(stats["misses"]) >= 1
    time.sleep(0.08)
    assert cache.get("btc") is None
