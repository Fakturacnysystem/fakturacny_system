from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Iterable
import math


def _safe_list(values: Iterable[float]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            fv = float(v)
            if math.isfinite(fv):
                out.append(fv)
        except Exception:
            pass
    return out


@dataclass
class DriftDetector:
    psi_threshold: float = 0.2

    def psi(self, expected: Iterable[float], actual: Iterable[float], bins: int = 10) -> float:
        exp = _safe_list(expected)
        act = _safe_list(actual)

        if len(exp) < 2 or len(act) < 2:
            return 0.0

        all_vals = exp + act
        lo = min(all_vals)
        hi = max(all_vals)

        if lo == hi:
            return 0.0

        step = (hi - lo) / bins
        if step <= 0:
            return 0.0

        edges = [lo + i * step for i in range(bins + 1)]

        def bucketize(vals: list[float]) -> list[float]:
            counts = [0] * bins
            for v in vals:
                idx = bins - 1 if v >= edges[-1] else int((v - lo) / step)
                idx = max(0, min(idx, bins - 1))
                counts[idx] += 1
            total = sum(counts) or 1
            return [max(c / total, 1e-6) for c in counts]

        p = bucketize(exp)
        q = bucketize(act)

        psi_value = 0.0
        for pi, qi in zip(p, q):
            psi_value += (qi - pi) * math.log(qi / pi)
        return float(psi_value)


@dataclass
class ModelRecord:
    version: str
    metrics: dict
    canary: bool
    promoted: bool
    metadata: dict
    artifact_hash: str
    created_at: str


class ModelRegistry:
    def __init__(self) -> None:
        self._records: dict[str, ModelRecord] = {}
        self._latest_stable_version: str | None = None

    def register(self, version: str, metrics: dict, canary: bool, metadata: dict) -> ModelRecord:
        payload = {"version": version, "metrics": metrics, "canary": canary, "metadata": metadata}
        artifact_hash = sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        record = ModelRecord(
            version=version,
            metrics=dict(metrics),
            canary=bool(canary),
            promoted=not bool(canary),
            metadata=dict(metadata),
            artifact_hash=artifact_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._records[version] = record
        if not canary:
            self._latest_stable_version = version
        return record

    def promote(self, version: str) -> ModelRecord:
        if version not in self._records:
            raise ValueError(f"unknown_model_version:{version}")
        rec = self._records[version]
        rec.canary = False
        rec.promoted = True
        self._latest_stable_version = version
        return rec

    def latest_stable(self) -> ModelRecord | None:
        if self._latest_stable_version is None:
            return None
        return self._records.get(self._latest_stable_version)


@dataclass
class CanaryComparison:
    promote: bool
    rollback: bool
    reason: str
    details: dict = field(default_factory=dict)


@dataclass
class DeploymentAction:
    action: str
    reason: str
    throttle: float = 1.0


class MLOpsService:
    """
    Compatibility layer for orchestrator expectations.

    Exposes:
    - detector.psi(...)
    - should_rollback(...)
    """

    def __init__(self, rollback_dd_threshold_pct: float = 10.0, drift_psi_threshold: float = 0.2) -> None:
        self.rollback_dd_threshold_pct = float(rollback_dd_threshold_pct)
        self.drift_psi_threshold = float(drift_psi_threshold)
        self.detector = DriftDetector(psi_threshold=self.drift_psi_threshold)
        self.registry = ModelRegistry()

    def should_rollback(self, drawdown_pct: float, psi: float | None = None, psi_value: float | None = None) -> bool:
        try:
            dd = float(drawdown_pct)
        except Exception:
            dd = 0.0
        try:
            drift = float(psi if psi is not None else (psi_value if psi_value is not None else 0.0))
        except Exception:
            drift = 0.0

        return dd >= self.rollback_dd_threshold_pct or drift >= self.drift_psi_threshold

    def canary_risk_budget(self, total_risk_budget: float, canary_risk_pct: float) -> float:
        total = max(0.0, float(total_risk_budget))
        pct = max(0.0, min(1.0, float(canary_risk_pct)))
        return total * pct

    def register_model(self, version: str, metrics: dict, canary: bool = True, metadata: dict | None = None) -> ModelRecord:
        return self.registry.register(version=version, metrics=metrics, canary=canary, metadata=metadata or {})

    def promote_canary(self, version: str) -> ModelRecord:
        return self.registry.promote(version)

    def compare_canary(self, baseline_metrics: dict, canary_metrics: dict, psi_value: float) -> CanaryComparison:
        baseline_net = float(baseline_metrics.get("net_after_costs_bps", 0.0))
        canary_net = float(canary_metrics.get("net_after_costs_bps", 0.0))
        baseline_dd = float(baseline_metrics.get("drawdown_pct", 0.0))
        canary_dd = float(canary_metrics.get("drawdown_pct", 0.0))
        baseline_slip = max(1e-9, float(baseline_metrics.get("slippage_bps", 0.0)))
        canary_slip = float(canary_metrics.get("slippage_bps", 0.0))
        baseline_funding = max(1e-9, float(baseline_metrics.get("funding_paid_pct", 0.0)))
        canary_funding = float(canary_metrics.get("funding_paid_pct", 0.0))

        if self.should_rollback(drawdown_pct=canary_dd, psi_value=psi_value):
            return CanaryComparison(
                promote=False,
                rollback=True,
                reason="rollback_canary",
                details={"drawdown_pct": canary_dd, "psi": psi_value},
            )

        net_better = canary_net > (baseline_net + 0.2)
        drawdown_not_worse = canary_dd <= max(baseline_dd + 0.3, baseline_dd * 1.2)
        slippage_not_worse = canary_slip <= (baseline_slip * 1.4)
        funding_not_worse = canary_funding <= (baseline_funding * 1.4)

        if net_better and drawdown_not_worse and slippage_not_worse and funding_not_worse:
            return CanaryComparison(
                promote=True,
                rollback=False,
                reason="promote_canary",
                details={
                    "net_after_costs_bps_baseline": baseline_net,
                    "net_after_costs_bps_canary": canary_net,
                    "drawdown_pct_baseline": baseline_dd,
                    "drawdown_pct_canary": canary_dd,
                },
            )

        return CanaryComparison(
            promote=False,
            rollback=False,
            reason="hold_canary",
            details={
                "net_after_costs_bps_baseline": baseline_net,
                "net_after_costs_bps_canary": canary_net,
                "drawdown_pct_baseline": baseline_dd,
                "drawdown_pct_canary": canary_dd,
                "slippage_bps_baseline": baseline_slip,
                "slippage_bps_canary": canary_slip,
                "funding_paid_pct_baseline": baseline_funding,
                "funding_paid_pct_canary": canary_funding,
            },
        )

    def deployment_action(self, drawdown_pct: float, psi_value: float, performance_drift: float) -> DeploymentAction:
        if self.should_rollback(drawdown_pct=drawdown_pct, psi_value=psi_value):
            return DeploymentAction(action="safe_mode", reason="rollback_trigger", throttle=0.0)
        if float(performance_drift) >= 0.05:
            return DeploymentAction(action="throttle", reason="performance_drift", throttle=0.5)
        return DeploymentAction(action="continue", reason="stable", throttle=1.0)

    def evaluate(self, drawdown_pct: float, psi: float) -> dict:
        rollback = self.should_rollback(drawdown_pct, psi)
        return {
            "rollback": rollback,
            "drawdown_pct": float(drawdown_pct),
            "psi": float(psi),
            "rollback_dd_threshold_pct": self.rollback_dd_threshold_pct,
            "drift_psi_threshold": self.drift_psi_threshold,
        }
