from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json


@dataclass
class ModelRecord:
    version: str
    score: float
    canary: bool
    metrics: dict[str, float] = field(default_factory=dict)
    artifact_hash: str = ""
    promoted: bool = False
    rolled_back: bool = False


class ModelRegistry:
    def __init__(self) -> None:
        self.models: list[ModelRecord] = [ModelRecord(version="baseline", score=0.0, canary=False, promoted=True)]

    def register(self, version: str, score: float, canary: bool = True, metrics: dict[str, float] | None = None, artifact_hash: str = "") -> ModelRecord:
        rec = ModelRecord(version=version, score=score, canary=canary, metrics=metrics or {}, artifact_hash=artifact_hash)
        self.models.append(rec)
        return rec

    def latest_stable(self) -> ModelRecord:
        stable = [m for m in self.models if not m.canary]
        return stable[-1] if stable else self.models[0]

    def latest_canary(self) -> ModelRecord | None:
        canaries = [m for m in self.models if m.canary]
        return canaries[-1] if canaries else None

    def promote(self, version: str) -> ModelRecord:
        for i, m in enumerate(self.models):
            if m.version == version:
                promoted = ModelRecord(
                    version=m.version,
                    score=m.score,
                    canary=False,
                    metrics=dict(m.metrics),
                    artifact_hash=m.artifact_hash,
                    promoted=True,
                    rolled_back=False,
                )
                self.models.append(promoted)
                return promoted
        raise ValueError(f"unknown_model:{version}")

    def mark_rollback(self, version: str) -> None:
        for m in self.models:
            if m.version == version:
                m.rolled_back = True
                return
        raise ValueError(f"unknown_model:{version}")


class DriftDetector:
    def psi(self, reference: list[float], current: list[float]) -> float:
        if not reference or not current:
            return 0.0
        mr = sum(reference) / len(reference)
        mc = sum(current) / len(current)
        return abs(mc - mr) / (abs(mr) + 1e-9)

    def performance_drift(self, baseline_net_after_cost_bps: float, current_net_after_cost_bps: float) -> float:
        denom = abs(baseline_net_after_cost_bps) + 1e-9
        return (baseline_net_after_cost_bps - current_net_after_cost_bps) / denom


@dataclass
class CanaryComparison:
    promote: bool
    rollback: bool
    reason: str
    details: dict[str, float]


@dataclass
class DeployDecision:
    action: str
    reason: str
    risk_multiplier: float


class MLOpsService:
    def __init__(self, rollback_dd_threshold_pct: float, drift_psi_threshold: float) -> None:
        self.registry = ModelRegistry()
        self.rollback_dd_threshold_pct = rollback_dd_threshold_pct
        self.drift_psi_threshold = drift_psi_threshold
        self.detector = DriftDetector()

    def canary_risk_budget(self, total_risk_budget: float, canary_pct: float) -> float:
        return max(0.0, total_risk_budget * canary_pct)

    def model_artifact_hash(self, metadata: dict) -> str:
        payload = json.dumps(metadata, sort_keys=True, default=str)
        return sha256(payload.encode("utf-8")).hexdigest()

    def register_model(self, version: str, *, metrics: dict[str, float], canary: bool = True, metadata: dict | None = None) -> ModelRecord:
        artifact_hash = self.model_artifact_hash(metadata or {"version": version, "metrics": metrics})
        score = float(metrics.get("net_after_costs_bps", metrics.get("score", 0.0)))
        return self.registry.register(version=version, score=score, canary=canary, metrics=metrics, artifact_hash=artifact_hash)

    def compare_canary(
        self,
        *,
        baseline_metrics: dict[str, float],
        canary_metrics: dict[str, float],
        dd_not_worse_tolerance_pct: float = 0.25,
        slippage_not_worse_tolerance_bps: float = 1.0,
        funding_not_worse_tolerance_pct: float = 0.05,
        psi_value: float = 0.0,
    ) -> CanaryComparison:
        b_net = float(baseline_metrics.get("net_after_costs_bps", 0.0))
        c_net = float(canary_metrics.get("net_after_costs_bps", 0.0))
        b_dd = float(baseline_metrics.get("drawdown_pct", 0.0))
        c_dd = float(canary_metrics.get("drawdown_pct", 0.0))
        b_slip = float(baseline_metrics.get("slippage_bps", 0.0))
        c_slip = float(canary_metrics.get("slippage_bps", 0.0))
        b_funding = float(baseline_metrics.get("funding_paid_pct", 0.0))
        c_funding = float(canary_metrics.get("funding_paid_pct", 0.0))

        net_up = c_net > b_net
        dd_ok = c_dd <= (b_dd + dd_not_worse_tolerance_pct)
        slip_ok = c_slip <= (b_slip + slippage_not_worse_tolerance_bps)
        funding_ok = c_funding <= (b_funding + funding_not_worse_tolerance_pct)
        drift_ok = psi_value <= self.drift_psi_threshold

        if net_up and dd_ok and slip_ok and funding_ok and drift_ok:
            return CanaryComparison(
                promote=True,
                rollback=False,
                reason="promote_canary",
                details={
                    "baseline_net_after_costs_bps": b_net,
                    "canary_net_after_costs_bps": c_net,
                    "psi_value": psi_value,
                },
            )

        perf_drift = self.detector.performance_drift(b_net, c_net)
        if (not drift_ok) or perf_drift > 0.1 or not dd_ok:
            return CanaryComparison(
                promote=False,
                rollback=True,
                reason="rollback_canary",
                details={
                    "performance_drift": perf_drift,
                    "psi_value": psi_value,
                    "dd_ok": 1.0 if dd_ok else 0.0,
                    "slip_ok": 1.0 if slip_ok else 0.0,
                    "funding_ok": 1.0 if funding_ok else 0.0,
                },
            )

        return CanaryComparison(
            promote=False,
            rollback=False,
            reason="hold_canary",
            details={
                "performance_drift": perf_drift,
                "psi_value": psi_value,
            },
        )

    def promote_canary(self, version: str) -> ModelRecord:
        return self.registry.promote(version)

    def rollback_model(self, version: str) -> None:
        self.registry.mark_rollback(version)

    def should_rollback(self, drawdown_pct: float, psi_value: float) -> bool:
        return drawdown_pct > self.rollback_dd_threshold_pct or psi_value > self.drift_psi_threshold

    def deployment_action(self, *, drawdown_pct: float, psi_value: float, performance_drift: float = 0.0) -> DeployDecision:
        if psi_value > self.drift_psi_threshold or performance_drift > 0.15:
            return DeployDecision(action="safe_mode", reason="drift_or_perf_degradation", risk_multiplier=0.0)
        if drawdown_pct > self.rollback_dd_threshold_pct:
            return DeployDecision(action="rollback", reason="drawdown_limit", risk_multiplier=0.0)
        if performance_drift > 0.05:
            return DeployDecision(action="throttle", reason="performance_drift_warning", risk_multiplier=0.5)
        return DeployDecision(action="keep", reason="healthy", risk_multiplier=1.0)
