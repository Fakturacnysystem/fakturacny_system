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
class DriftAlert:
    alert_id: str
    severity: str
    drift_score: float
    stale_data: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "severity": self.severity,
            "drift_score": float(self.drift_score),
            "stale_data": bool(self.stale_data),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class CalibrationState:
    calibration_id: str
    deterministic: bool
    input_confidence: float
    calibrated_confidence: float
    freshness_penalty: float
    drift_score: float
    stale_data: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    alerts: tuple[DriftAlert, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "calibration_id": self.calibration_id,
            "deterministic": bool(self.deterministic),
            "input_confidence": float(self.input_confidence),
            "calibrated_confidence": float(self.calibrated_confidence),
            "freshness_penalty": float(self.freshness_penalty),
            "drift_score": float(self.drift_score),
            "stale_data": bool(self.stale_data),
            "reason_codes": [str(item) for item in self.reason_codes],
            "alerts": [row.to_dict() for row in self.alerts],
        }


class GlobalMarketCalibrationEngine:
    """Phase 39 deterministic confidence calibration and drift sentinel."""

    def calibrate(
        self,
        *,
        global_market_state: Mapping[str, Any] | None,
    ) -> CalibrationState:
        state = _safe_mapping(global_market_state)
        confidence = _safe_mapping(state.get("confidence", {}))
        freshness = _safe_mapping(state.get("freshness", {}))
        input_conf = _clamp(_safe_float(confidence.get("overall", 0.0), 0.0), 0.0, 1.0)
        stale_components = freshness.get("stale_components", [])
        stale_list = [str(item) for item in stale_components] if isinstance(stale_components, list) else []
        max_age_s = max(0.0, _safe_float(freshness.get("max_age_s", 0.0), 0.0))
        stale_penalty = _clamp((len(stale_list) * 0.12) + max(0.0, (max_age_s - 60.0) / 900.0), 0.0, 0.70)
        market_stress = _clamp(_safe_float(state.get("market_stress", 0.0), 0.0), 0.0, 1.0)
        risk_on_score = _clamp(_safe_float(state.get("risk_on_score", 0.0), 0.0), 0.0, 1.0)
        partial_data = bool(state.get("partial_data", False))
        drift_score = _clamp(
            abs(market_stress - (1.0 - risk_on_score)) * 0.55
            + stale_penalty * 0.30
            + (0.15 if partial_data else 0.0),
            0.0,
            1.0,
        )
        calibrated_conf = _clamp(input_conf - stale_penalty - drift_score * 0.25, 0.0, input_conf)
        stale_data = bool(stale_list or partial_data or max_age_s > 300.0)
        reasons: list[str] = []
        if stale_data:
            reasons.append("stale_input_confidence_degraded")
        if stale_list:
            reasons.extend([f"stale_component:{item}" for item in sorted(stale_list)])
        if partial_data:
            reasons.append("partial_data")
        if drift_score >= 0.45:
            reasons.append("drift_score_elevated")
        if not reasons:
            reasons.append("calibration_stable")
        severity = "critical" if drift_score >= 0.75 else "high" if drift_score >= 0.55 else "medium" if stale_data else "low"
        alert = DriftAlert(
            alert_id=_stable_hash(
                {
                    "phase": 39,
                    "drift_score": round(drift_score, 6),
                    "stale_data": bool(stale_data),
                    "severity": severity,
                    "stale_components": sorted(stale_list),
                }
            )[:24],
            severity=severity,
            drift_score=drift_score,
            stale_data=stale_data,
            reason_codes=tuple(reasons),
        )
        calibration_id = _stable_hash(
            {
                "phase": 39,
                "input_confidence": round(input_conf, 6),
                "calibrated_confidence": round(calibrated_conf, 6),
                "freshness_penalty": round(stale_penalty, 6),
                "drift_score": round(drift_score, 6),
                "stale_data": bool(stale_data),
                "reason_codes": sorted(set(reasons)),
            }
        )[:24]
        return CalibrationState(
            calibration_id=calibration_id,
            deterministic=True,
            input_confidence=input_conf,
            calibrated_confidence=calibrated_conf,
            freshness_penalty=stale_penalty,
            drift_score=drift_score,
            stale_data=stale_data,
            reason_codes=tuple(dict.fromkeys(reasons)),
            alerts=(alert,),
        )
