from __future__ import annotations

from datetime import datetime

from autonomous_investment_robot.core.contracts import InterferenceScore, SignalInterferenceReport


def build_interference_report(*, symbol: str, ts: datetime, forecast: object, alpha_signals: list[object]) -> SignalInterferenceReport:
    forecast_sign = 1.0 if float(getattr(forecast, "mu", 0.0)) >= 0.0 else -1.0
    reinforcement = 0.0
    conflict = 0.0
    scores: list[InterferenceScore] = []
    for signal in alpha_signals:
        directional = float(getattr(signal, "directional_probability", 0.5)) - 0.5
        expected_move = float(getattr(signal, "expected_move_bps", 0.0))
        confidence = float(getattr(signal, "confidence", 0.0))
        regime_fit = float(getattr(signal, "regime_fit", 0.0))
        execution_risk = float(getattr(signal, "execution_risk", 0.0))
        contribution = directional * expected_move * max(0.1, confidence) * max(0.1, regime_fit) * max(0.1, 1.0 - execution_risk)
        agreement = 1.0 if contribution == 0.0 else (1.0 if contribution * forecast_sign >= 0.0 else -1.0)
        if agreement >= 0.0:
            reinforcement += abs(contribution)
        else:
            conflict += abs(contribution)
        scores.append(
            InterferenceScore(
                signal_name=str(getattr(signal, "expert_name", "unknown")),
                contribution=contribution,
                agreement=agreement,
                metadata={"execution_risk": execution_risk},
            )
        )
    total = max(reinforcement + conflict, 1e-9)
    uncertainty_penalty = min(1.0, conflict / total)
    return SignalInterferenceReport(
        symbol=symbol,
        ts=ts,
        reinforcement_score=reinforcement,
        conflict_score=conflict,
        net_score=reinforcement - conflict,
        uncertainty_penalty=uncertainty_penalty,
        scores=scores,
        metadata={"heuristic": True},
    )
