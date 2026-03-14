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
class PostureContraction:
    size_scale: float
    risk_scale: float
    urgency_cap: str
    allow_taker: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "size_scale": float(self.size_scale),
            "risk_scale": float(self.risk_scale),
            "urgency_cap": self.urgency_cap,
            "allow_taker": bool(self.allow_taker),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class MacroMicroBridgeDecision:
    bridge_id: str
    deterministic: bool
    macro_stress: float
    calibrated_confidence: float
    contraction: PostureContraction
    recommended_execution_mode: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bridge_id": self.bridge_id,
            "deterministic": bool(self.deterministic),
            "macro_stress": float(self.macro_stress),
            "calibrated_confidence": float(self.calibrated_confidence),
            "contraction": self.contraction.to_dict(),
            "recommended_execution_mode": self.recommended_execution_mode,
            "reason_codes": [str(item) for item in self.reason_codes],
        }


class MacroMicroDecisionBridge:
    """Phase 44 deterministic macro-to-micro posture contraction."""

    def bridge(
        self,
        *,
        global_market_state: Mapping[str, Any] | None,
        calibration_state: Mapping[str, Any] | None,
        capital_constraints: Mapping[str, Any] | None,
        execution_intelligence: Mapping[str, Any] | None,
    ) -> MacroMicroBridgeDecision:
        macro = _safe_mapping(global_market_state)
        calibration = _safe_mapping(calibration_state)
        constraints = _safe_mapping(capital_constraints)
        execution = _safe_mapping(execution_intelligence)
        macro_stress = _clamp(_safe_float(macro.get("market_stress", 0.0), 0.0), 0.0, 1.0)
        calibrated_conf = _clamp(
            _safe_float(calibration.get("calibrated_confidence", macro.get("confidence", 0.5)), 0.5),
            0.0,
            1.0,
        )
        hard_clamp = bool(constraints.get("hard_clamp", False))
        non_positive_edge = _safe_float(_safe_mapping(execution.get("quality_estimate", {})).get("expected_net_edge_bps", 0.0), 0.0) <= 0.0
        reason_codes: list[str] = []

        size_scale = _clamp(1.0 - macro_stress * 0.60, 0.05, 1.0)
        risk_scale = _clamp(1.0 - macro_stress * 0.55, 0.05, 1.0)
        if calibrated_conf < 0.60:
            shrink = (0.60 - calibrated_conf) * 0.80
            size_scale = _clamp(size_scale - shrink, 0.05, 1.0)
            risk_scale = _clamp(risk_scale - shrink, 0.05, 1.0)
            reason_codes.append("calibration_confidence_contraction")
        if hard_clamp:
            size_scale = 0.0
            risk_scale = 0.0
            reason_codes.append("capital_constraints_hard_clamp")
        urgency_cap = "high"
        if macro_stress >= 0.75 or calibrated_conf <= 0.45:
            urgency_cap = "low"
            reason_codes.append("macro_stress_high")
        elif macro_stress >= 0.55:
            urgency_cap = "medium"
            reason_codes.append("macro_stress_elevated")
        allow_taker = bool((not hard_clamp) and (not non_positive_edge) and macro_stress < 0.80)
        if not allow_taker:
            reason_codes.append("taker_flow_restricted")
        recommended_mode = "hold" if hard_clamp else "defensive" if urgency_cap in {"low", "medium"} else "normal"
        if not reason_codes:
            reason_codes.append("macro_micro_bridge_stable")
        contraction = PostureContraction(
            size_scale=size_scale,
            risk_scale=risk_scale,
            urgency_cap=urgency_cap,
            allow_taker=allow_taker,
            reason_codes=tuple(reason_codes),
        )
        bridge_id = _stable_hash(
            {
                "phase": 44,
                "macro_stress": round(macro_stress, 6),
                "calibrated_confidence": round(calibrated_conf, 6),
                "size_scale": round(size_scale, 6),
                "risk_scale": round(risk_scale, 6),
                "urgency_cap": urgency_cap,
                "allow_taker": bool(allow_taker),
                "reasons": sorted(set(reason_codes)),
            }
        )[:24]
        return MacroMicroBridgeDecision(
            bridge_id=bridge_id,
            deterministic=True,
            macro_stress=macro_stress,
            calibrated_confidence=calibrated_conf,
            contraction=contraction,
            recommended_execution_mode=recommended_mode,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
        )
