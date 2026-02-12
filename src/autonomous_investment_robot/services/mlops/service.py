from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelRecord:
    version: str
    score: float
    canary: bool


class ModelRegistry:
    def __init__(self) -> None:
        self.models: list[ModelRecord] = [ModelRecord(version="baseline", score=0.0, canary=False)]

    def register(self, version: str, score: float, canary: bool = True) -> None:
        self.models.append(ModelRecord(version=version, score=score, canary=canary))

    def latest_stable(self) -> ModelRecord:
        stable = [m for m in self.models if not m.canary]
        return stable[-1] if stable else self.models[0]


class DriftDetector:
    def psi(self, reference: list[float], current: list[float]) -> float:
        if not reference or not current:
            return 0.0
        mr = sum(reference) / len(reference)
        mc = sum(current) / len(current)
        return abs(mc - mr) / (abs(mr) + 1e-9)


class MLOpsService:
    def __init__(self, rollback_dd_threshold_pct: float, drift_psi_threshold: float) -> None:
        self.registry = ModelRegistry()
        self.rollback_dd_threshold_pct = rollback_dd_threshold_pct
        self.drift_psi_threshold = drift_psi_threshold
        self.detector = DriftDetector()

    def should_rollback(self, drawdown_pct: float, psi_value: float) -> bool:
        return drawdown_pct < -self.rollback_dd_threshold_pct or psi_value > self.drift_psi_threshold
