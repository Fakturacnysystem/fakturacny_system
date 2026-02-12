from __future__ import annotations

from autonomous_investment_robot.core.contracts import FeatureVector


class FeatureStoreService:
    def __init__(self, feature_version: str = "v1-default") -> None:
        self.feature_version = feature_version

    def build(self, symbol: str, ts, raw: dict) -> FeatureVector:
        values = {
            "ret_5m": float(raw.get("ret_5m", 0.0)),
            "realized_vol_1h": float(raw.get("realized_vol_1h", 0.0)),
            "depth_score": float(raw.get("depth_score", 0.0)),
        }
        return FeatureVector(feature_version=self.feature_version, symbol=symbol, ts=ts, values=values)

    def assert_no_leakage(self, feature_ts, label_ts) -> None:
        if feature_ts > label_ts:
            raise ValueError("Feature leakage detected: feature timestamp exceeds label timestamp")
