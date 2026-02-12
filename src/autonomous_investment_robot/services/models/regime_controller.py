from __future__ import annotations

from autonomous_investment_robot.services.policy.regime import detect_regime_state


def detect_regime(features: dict[str, float]) -> tuple[str, str, float]:
    r = detect_regime_state(features)
    return r.market, r.liquidity, r.confidence
