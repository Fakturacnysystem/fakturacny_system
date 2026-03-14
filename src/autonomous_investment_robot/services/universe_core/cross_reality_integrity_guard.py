from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IntegrityThresholdContract:
    min_component_coverage: float = 0.75
    max_normalization_drift: float = 0.45
    min_confidence: float = 0.40
    critical_components: tuple[str, ...] = ("derivatives", "social")

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_component_coverage": float(self.min_component_coverage),
            "max_normalization_drift": float(self.max_normalization_drift),
            "min_confidence": float(self.min_confidence),
            "critical_components": [str(item) for item in self.critical_components],
        }


@dataclass(frozen=True)
class IntegrityEscalationDecision:
    decision_id: str
    deterministic: bool
    integrity_ok: bool
    fail_closed: bool
    recommended_mode: str
    confidence_scale: float
    threshold: IntegrityThresholdContract
    observed: dict[str, Any] = field(default_factory=dict)
    escalation_reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "deterministic": bool(self.deterministic),
            "integrity_ok": bool(self.integrity_ok),
            "fail_closed": bool(self.fail_closed),
            "recommended_mode": self.recommended_mode,
            "confidence_scale": float(self.confidence_scale),
            "threshold": self.threshold.to_dict(),
            "observed": dict(self.observed),
            "escalation_reason_codes": [str(item) for item in self.escalation_reason_codes],
        }


class CrossRealityIntegrityGuard:
    """Phase 40 deterministic guard for cross-reality signal integrity."""

    def __init__(self, *, threshold: IntegrityThresholdContract | None = None) -> None:
        self.threshold = threshold or IntegrityThresholdContract()

    def assess(
        self,
        *,
        cross_reality_signal: Mapping[str, Any] | None,
    ) -> IntegrityEscalationDecision:
        payload = _safe_mapping(cross_reality_signal)
        integrity = _safe_mapping(payload.get("integrity", {}))
        confidence = _clamp(_safe_float(payload.get("confidence", 0.0), 0.0), 0.0, 1.0)
        coverage = _clamp(_safe_float(integrity.get("component_coverage", 0.0), 0.0), 0.0, 1.0)
        drift = _clamp(_safe_float(integrity.get("normalization_drift", 1.0), 1.0), 0.0, 1.0)
        missing = integrity.get("missing_components", [])
        missing_components = [str(item) for item in missing] if isinstance(missing, list) else []
        reasons: list[str] = []
        if coverage < self.threshold.min_component_coverage:
            reasons.append("low_component_coverage")
        if drift > self.threshold.max_normalization_drift:
            reasons.append("normalization_drift_high")
        if confidence < self.threshold.min_confidence:
            reasons.append("cross_reality_confidence_low")
        critical_missing = sorted(set(missing_components).intersection(set(self.threshold.critical_components)))
        if critical_missing:
            reasons.extend([f"missing_critical_component:{item}" for item in critical_missing])
        severe = bool(
            coverage < (self.threshold.min_component_coverage * 0.70)
            or drift > (self.threshold.max_normalization_drift + 0.20)
            or len(critical_missing) >= 1
        )
        fail_closed = bool(severe or (not payload))
        integrity_ok = len(reasons) == 0 and not fail_closed
        if not reasons:
            reasons.append("integrity_within_threshold")
        recommended_mode = "hard_stop" if fail_closed else "observe_only" if reasons != ["integrity_within_threshold"] else "normal"
        confidence_scale = 0.0 if fail_closed else 0.35 if recommended_mode == "observe_only" else 1.0
        observed = {
            "component_coverage": coverage,
            "normalization_drift": drift,
            "confidence": confidence,
            "missing_components": sorted(missing_components),
        }
        decision_id = _stable_hash(
            {
                "phase": 40,
                "coverage": round(coverage, 6),
                "drift": round(drift, 6),
                "confidence": round(confidence, 6),
                "fail_closed": bool(fail_closed),
                "reasons": sorted(set(reasons)),
            }
        )[:24]
        return IntegrityEscalationDecision(
            decision_id=decision_id,
            deterministic=True,
            integrity_ok=integrity_ok,
            fail_closed=fail_closed,
            recommended_mode=recommended_mode,
            confidence_scale=confidence_scale,
            threshold=self.threshold,
            observed=observed,
            escalation_reason_codes=tuple(dict.fromkeys(reasons)),
        )
