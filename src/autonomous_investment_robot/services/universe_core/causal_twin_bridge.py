from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping

from autonomous_investment_robot.services.autonomous_decision.causal_market_twin import score_causal_hypotheses


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
class TwinDivergenceSignal:
    signal_id: str
    divergence_score: float
    severity: str
    stale_input: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "divergence_score": float(self.divergence_score),
            "severity": self.severity,
            "stale_input": bool(self.stale_input),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class CausalScenarioAlignment:
    alignment_id: str
    deterministic: bool
    conservative_fallback: bool
    alignment_score: float
    scenario_confidence: float
    twin_confidence: float
    divergence_signal: TwinDivergenceSignal
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    observed: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alignment_id": self.alignment_id,
            "deterministic": bool(self.deterministic),
            "conservative_fallback": bool(self.conservative_fallback),
            "alignment_score": float(self.alignment_score),
            "scenario_confidence": float(self.scenario_confidence),
            "twin_confidence": float(self.twin_confidence),
            "divergence_signal": self.divergence_signal.to_dict(),
            "reason_codes": [str(item) for item in self.reason_codes],
            "observed": dict(self.observed),
        }


class CausalTwinBridge:
    """Phase 46 deterministic coupling between ensemble scenarios and causal twin diagnostics."""

    def __init__(self, *, max_twin_age_s: float = 120.0) -> None:
        self.max_twin_age_s = max(10.0, float(max_twin_age_s))

    def align(
        self,
        *,
        simulation_ensemble: Mapping[str, Any] | None,
        twin_state: Mapping[str, Any] | None,
    ) -> CausalScenarioAlignment:
        ensemble = _safe_mapping(simulation_ensemble)
        twin = _safe_mapping(twin_state)
        twin_as_of = _safe_float(twin.get("as_of_ts", 0.0), 0.0)
        twin_reference_ts = _safe_float(twin.get("reference_ts", twin_as_of), twin_as_of)
        twin_age_s = max(0.0, twin_reference_ts - twin_as_of) if twin_as_of > 0.0 else 0.0
        explicit_stale = bool(twin.get("stale", False))
        stale_input = bool(explicit_stale or twin_age_s > self.max_twin_age_s)
        trees = ensemble.get("trees", [])
        tree_count = len(trees) if isinstance(trees, list) else 0
        scenario_confidence = _clamp(
            _safe_float(_safe_mapping(ensemble.get("confidence", {})).get("overall_confidence", 0.0), 0.0),
            0.0,
            1.0,
        )
        if stale_input or not twin:
            divergence = TwinDivergenceSignal(
                signal_id=_stable_hash({"phase": 46, "stale_input": True, "tree_count": tree_count})[:24],
                divergence_score=1.0,
                severity="critical",
                stale_input=True,
                reason_codes=("twin_input_stale_or_missing",),
            )
            alignment_id = _stable_hash(
                {"phase": 46, "fallback": True, "tree_count": tree_count, "scenario_confidence": scenario_confidence}
            )[:24]
            return CausalScenarioAlignment(
                alignment_id=alignment_id,
                deterministic=True,
                conservative_fallback=True,
                alignment_score=0.0,
                scenario_confidence=scenario_confidence,
                twin_confidence=0.0,
                divergence_signal=divergence,
                reason_codes=("conservative_fallback_stale_twin",),
                observed={
                    "twin_age_s": twin_age_s,
                    "tree_count": tree_count,
                },
            )
        twin_scores = score_causal_hypotheses(twin)
        twin_risk_proxy = _clamp(
            _safe_float(twin_scores.get("volatility_shock", 0.0), 0.0) * 0.45
            + _safe_float(twin_scores.get("fake_breakout_risk", 0.0), 0.0) * 0.35
            + _safe_float(twin_scores.get("liquidity_squeeze_breakout", 0.0), 0.0) * 0.20,
            0.0,
            1.0,
        )
        aggregate = _safe_mapping(ensemble.get("aggregate_pnl_envelope", {}))
        worst_case = abs(min(0.0, _safe_float(aggregate.get("worst_case", 0.0), 0.0)))
        expected = abs(_safe_float(aggregate.get("expected", 0.0), 0.0))
        scenario_risk_proxy = _clamp(worst_case / max(1e-6, (worst_case + expected + 1e-6)), 0.0, 1.0)
        alignment_score = _clamp(1.0 - abs(twin_risk_proxy - scenario_risk_proxy), 0.0, 1.0)
        divergence_score = _clamp(1.0 - alignment_score, 0.0, 1.0)
        twin_confidence = _clamp(_safe_float(twin.get("confidence", 0.5), 0.5), 0.0, 1.0)
        reasons: list[str] = []
        if divergence_score >= 0.65:
            reasons.append("twin_simulation_divergence_high")
        elif divergence_score >= 0.45:
            reasons.append("twin_simulation_divergence_elevated")
        else:
            reasons.append("twin_simulation_alignment_stable")
        severity = "critical" if divergence_score >= 0.80 else "high" if divergence_score >= 0.65 else "medium" if divergence_score >= 0.45 else "low"
        divergence = TwinDivergenceSignal(
            signal_id=_stable_hash(
                {
                    "phase": 46,
                    "divergence_score": round(divergence_score, 6),
                    "severity": severity,
                    "stale_input": False,
                    "tree_count": tree_count,
                }
            )[:24],
            divergence_score=divergence_score,
            severity=severity,
            stale_input=False,
            reason_codes=tuple(reasons),
        )
        alignment_id = _stable_hash(
            {
                "phase": 46,
                "alignment_score": round(alignment_score, 6),
                "scenario_confidence": round(scenario_confidence, 6),
                "twin_confidence": round(twin_confidence, 6),
                "tree_count": tree_count,
                "reasons": sorted(set(reasons)),
            }
        )[:24]
        return CausalScenarioAlignment(
            alignment_id=alignment_id,
            deterministic=True,
            conservative_fallback=False,
            alignment_score=alignment_score,
            scenario_confidence=scenario_confidence,
            twin_confidence=twin_confidence,
            divergence_signal=divergence,
            reason_codes=tuple(dict.fromkeys(reasons)),
            observed={
                "tree_count": tree_count,
                "scenario_risk_proxy": scenario_risk_proxy,
                "twin_risk_proxy": twin_risk_proxy,
                "twin_age_s": twin_age_s,
            },
        )
