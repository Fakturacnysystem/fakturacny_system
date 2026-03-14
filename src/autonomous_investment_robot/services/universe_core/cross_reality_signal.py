from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class DerivativesPressure:
    funding_rate: float
    open_interest_delta: float
    basis_bps: float
    pressure_score: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "funding_rate": float(self.funding_rate),
            "open_interest_delta": float(self.open_interest_delta),
            "basis_bps": float(self.basis_bps),
            "pressure_score": float(self.pressure_score),
            "confidence": float(self.confidence),
        }


@dataclass(frozen=True)
class OnChainFlowPressure:
    net_exchange_flow: float
    whale_flow_score: float
    pressure_score: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "net_exchange_flow": float(self.net_exchange_flow),
            "whale_flow_score": float(self.whale_flow_score),
            "pressure_score": float(self.pressure_score),
            "confidence": float(self.confidence),
        }


@dataclass(frozen=True)
class SocialPanicIndex:
    panic_score: float
    message_velocity: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "panic_score": float(self.panic_score),
            "message_velocity": float(self.message_velocity),
            "confidence": float(self.confidence),
        }


@dataclass(frozen=True)
class VolSurfaceDeformation:
    skew_change: float
    term_structure_stress: float
    deformation_score: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "skew_change": float(self.skew_change),
            "term_structure_stress": float(self.term_structure_stress),
            "deformation_score": float(self.deformation_score),
            "confidence": float(self.confidence),
        }


@dataclass(frozen=True)
class FusionIntegrityReport:
    component_coverage: float
    missing_components: tuple[str, ...] = field(default_factory=tuple)
    normalization_drift: float = 0.0
    deterministic: bool = True
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_coverage": float(self.component_coverage),
            "missing_components": [str(item) for item in self.missing_components],
            "normalization_drift": float(self.normalization_drift),
            "deterministic": bool(self.deterministic),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class CrossRealitySignal:
    derivatives: DerivativesPressure
    on_chain: OnChainFlowPressure
    social: SocialPanicIndex
    vol_surface: VolSurfaceDeformation
    composite_pressure: float
    confidence: float
    regime_tilt: str
    integrity: FusionIntegrityReport
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "derivatives": self.derivatives.to_dict(),
            "on_chain": self.on_chain.to_dict(),
            "social": self.social.to_dict(),
            "vol_surface": self.vol_surface.to_dict(),
            "composite_pressure": float(self.composite_pressure),
            "confidence": float(self.confidence),
            "regime_tilt": self.regime_tilt,
            "integrity": self.integrity.to_dict(),
            "diagnostics": dict(self.diagnostics),
        }


class CrossRealitySignalFusion:
    """Phase 30 deterministic normalization across derivatives/on-chain/social/vol surfaces."""

    def fuse(self, *, payload: Mapping[str, Any] | None = None) -> CrossRealitySignal:
        raw = _safe_mapping(payload)
        der_raw = _safe_mapping(raw.get("derivatives", {}))
        chain_raw = _safe_mapping(raw.get("on_chain", {}))
        social_raw = _safe_mapping(raw.get("social", {}))
        vol_raw = _safe_mapping(raw.get("vol_surface", {}))

        missing: list[str] = []
        if not der_raw:
            missing.append("derivatives")
        if not chain_raw:
            missing.append("on_chain")
        if not social_raw:
            missing.append("social")
        if not vol_raw:
            missing.append("vol_surface")

        derivatives = DerivativesPressure(
            funding_rate=_safe_float(der_raw.get("funding_rate", 0.0), 0.0),
            open_interest_delta=_safe_float(der_raw.get("open_interest_delta", 0.0), 0.0),
            basis_bps=_safe_float(der_raw.get("basis_bps", 0.0), 0.0),
            pressure_score=_clamp(
                _safe_float(
                    der_raw.get("pressure_score", (abs(_safe_float(der_raw.get("funding_rate", 0.0), 0.0)) * 8.0)),
                    0.0,
                ),
                0.0,
                1.0,
            ),
            confidence=0.75 if der_raw else 0.20,
        )
        on_chain = OnChainFlowPressure(
            net_exchange_flow=_safe_float(chain_raw.get("net_exchange_flow", 0.0), 0.0),
            whale_flow_score=_clamp(_safe_float(chain_raw.get("whale_flow_score", 0.0), 0.0), 0.0, 1.0),
            pressure_score=_clamp(_safe_float(chain_raw.get("pressure_score", 0.0), 0.0), 0.0, 1.0),
            confidence=0.70 if chain_raw else 0.20,
        )
        social = SocialPanicIndex(
            panic_score=_clamp(_safe_float(social_raw.get("panic_score", 0.0), 0.0), 0.0, 1.0),
            message_velocity=max(0.0, _safe_float(social_raw.get("message_velocity", 0.0), 0.0)),
            confidence=0.65 if social_raw else 0.20,
        )
        vol_surface = VolSurfaceDeformation(
            skew_change=_safe_float(vol_raw.get("skew_change", 0.0), 0.0),
            term_structure_stress=_clamp(_safe_float(vol_raw.get("term_structure_stress", 0.0), 0.0), 0.0, 1.0),
            deformation_score=_clamp(_safe_float(vol_raw.get("deformation_score", 0.0), 0.0), 0.0, 1.0),
            confidence=0.75 if vol_raw else 0.20,
        )
        components = {
            "derivatives": derivatives.pressure_score,
            "on_chain": on_chain.pressure_score,
            "social": social.panic_score,
            "vol_surface": vol_surface.deformation_score,
        }
        composite = _clamp(
            components["derivatives"] * 0.30
            + components["on_chain"] * 0.25
            + components["social"] * 0.20
            + components["vol_surface"] * 0.25,
            0.0,
            1.0,
        )
        confidence = _clamp(
            derivatives.confidence * 0.30
            + on_chain.confidence * 0.25
            + social.confidence * 0.20
            + vol_surface.confidence * 0.25,
            0.05,
            1.0,
        )
        coverage = 1.0 - (len(missing) / 4.0)
        drift = _clamp(abs(sum(components.values()) / 4.0 - composite), 0.0, 1.0)
        reason_codes: list[str] = []
        if missing:
            reason_codes.append("partial_component_coverage")
        if drift > 0.40:
            reason_codes.append("normalization_drift_high")
        integrity = FusionIntegrityReport(
            component_coverage=coverage,
            missing_components=tuple(sorted(missing)),
            normalization_drift=drift,
            deterministic=True,
            reason_codes=tuple(reason_codes),
        )
        tilt = "risk_off" if composite >= 0.65 else "neutral" if composite >= 0.35 else "risk_on"
        return CrossRealitySignal(
            derivatives=derivatives,
            on_chain=on_chain,
            social=social,
            vol_surface=vol_surface,
            composite_pressure=composite,
            confidence=confidence,
            regime_tilt=tilt,
            integrity=integrity,
            diagnostics={"phase": 30},
        )
