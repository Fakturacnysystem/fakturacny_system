from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt

from autonomous_investment_robot.services.data_ingestion.service import IngestedBar


@dataclass
class FeatureVector:
    symbol: str
    ts: datetime
    feature_version: str
    values: dict[str, float]


class FeatureStoreService:
    def __init__(self, feature_version: str = "v2-paper") -> None:
        self.feature_version = feature_version

    def build_from_bars(self, bars: list[IngestedBar]) -> list[FeatureVector]:
        out: list[FeatureVector] = []
        closes = [b.close for b in bars]
        for i, bar in enumerate(bars):
            ret_1 = 0.0 if i == 0 else (closes[i] / closes[i - 1] - 1.0)
            ret_3 = 0.0 if i < 3 else (closes[i] / closes[i - 3] - 1.0)
            window = closes[max(0, i - 5) : i + 1]
            mean = sum(window) / len(window)
            rv = sqrt(sum((x - mean) ** 2 for x in window) / len(window)) / mean if mean else 0.0
            atr = (bar.high - bar.low) / bar.close if bar.close else 0.0
            spread_proxy = (bar.high - bar.low) / ((bar.high + bar.low) / 2)
            out.append(
                FeatureVector(
                    symbol=bar.symbol,
                    ts=bar.ts,
                    feature_version=self.feature_version,
                    values={
                        "ret_1": ret_1,
                        "ret_3": ret_3,
                        "realized_vol": rv,
                        "atr_proxy": atr,
                        "spread_proxy": spread_proxy,
                    },
                )
            )
        return out

    def assert_no_leakage(self, feature_ts: datetime, label_ts: datetime) -> None:
        if feature_ts > label_ts:
            raise ValueError("Feature leakage detected")
