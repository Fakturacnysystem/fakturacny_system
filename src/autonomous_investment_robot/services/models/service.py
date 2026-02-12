from __future__ import annotations

from datetime import datetime, timezone
from math import log

from autonomous_investment_robot.core.contracts import ForecastDistribution, RegimeProbabilities


class ModelsService:
    def make_snapshot(self) -> dict:
        ts = datetime.now(timezone.utc)
        forecast = ForecastDistribution(
            model_version="ensemble-UNSPECIFIED",
            symbol="BTCUSDT",
            ts=ts,
            horizon="5m",
            mu=0.0,
            sigma=0.01,
            entropy=log(0.01 + 1e-9),
            quantiles={0.05: -0.01, 0.5: 0.0, 0.95: 0.01},
        )
        regime = RegimeProbabilities(ts=ts, probabilities={"trend": 0.4, "range": 0.6}, selected="range")
        return {"forecast": forecast, "regime": regime, "calibration": {"crps": 0.5, "pit_ok": True}}
