from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .global_market_brain import GlobalMarketState
from .multi_horizon_decision import HorizonAlignmentReport


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass(frozen=True)
class MomentumEnergy:
    score: float
    directional_bias: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": float(self.score),
            "directional_bias": float(self.directional_bias),
            "confidence": float(self.confidence),
        }


@dataclass(frozen=True)
class LiquidityFriction:
    coefficient: float
    drag: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "coefficient": float(self.coefficient),
            "drag": float(self.drag),
            "confidence": float(self.confidence),
        }


@dataclass(frozen=True)
class VolatilityTurbulence:
    intensity: float
    shock_probability: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "intensity": float(self.intensity),
            "shock_probability": float(self.shock_probability),
            "confidence": float(self.confidence),
        }


@dataclass(frozen=True)
class FundingGravity:
    force: float
    direction: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "force": float(self.force),
            "direction": self.direction,
            "confidence": float(self.confidence),
        }


@dataclass(frozen=True)
class EnergyInstabilitySignal:
    instability_score: float
    unstable: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instability_score": float(self.instability_score),
            "unstable": bool(self.unstable),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class MarketEnergyState:
    momentum: MomentumEnergy
    friction: LiquidityFriction
    turbulence: VolatilityTurbulence
    gravity: FundingGravity
    net_energy: float
    energy_balance: float
    instability: EnergyInstabilitySignal
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "momentum": self.momentum.to_dict(),
            "friction": self.friction.to_dict(),
            "turbulence": self.turbulence.to_dict(),
            "gravity": self.gravity.to_dict(),
            "net_energy": float(self.net_energy),
            "energy_balance": float(self.energy_balance),
            "instability": self.instability.to_dict(),
            "diagnostics": dict(self.diagnostics),
        }


class MarketEnergyPhysicsModel:
    """Phase 28 deterministic pseudo-physics decomposition of market state."""

    def assess(
        self,
        *,
        world: Any,
        global_market: GlobalMarketState,
        horizon: HorizonAlignmentReport,
    ) -> MarketEnergyState:
        market = getattr(world, "market_state", None)
        trend_bps = _safe_float(getattr(market, "trend_bias_bps", 0.0), 0.0)
        momentum_score = _clamp(abs(trend_bps) / 160.0 + horizon.tactical.opportunity_score * 0.25, 0.0, 1.0)
        direction = _clamp(trend_bps / 120.0, -1.0, 1.0)
        momentum = MomentumEnergy(
            score=momentum_score,
            directional_bias=direction,
            confidence=_clamp(horizon.tactical.confidence, 0.0, 1.0),
        )
        friction_coeff = _clamp(
            (1.0 - global_market.macro_liquidity.liquidity_score) * 0.60
            + global_market.cross_venue.spread_pressure * 0.25
            + global_market.cross_venue.depth_fragmentation * 0.15,
            0.0,
            1.0,
        )
        friction = LiquidityFriction(
            coefficient=friction_coeff,
            drag=_clamp(friction_coeff * (1.0 + abs(direction) * 0.25), 0.0, 1.25),
            confidence=_clamp(global_market.cross_venue.confidence, 0.0, 1.0),
        )
        realized_vol = _safe_float(getattr(market, "realized_vol", 0.0), 0.0)
        turbulence_intensity = _clamp(realized_vol / 0.04 + global_market.sentiment.panic_index * 0.30, 0.0, 1.0)
        turbulence = VolatilityTurbulence(
            intensity=turbulence_intensity,
            shock_probability=_clamp(turbulence_intensity * 0.70 + global_market.market_stress * 0.30, 0.0, 1.0),
            confidence=_clamp((global_market.sentiment.confidence + global_market.confidence.overall) / 2.0, 0.0, 1.0),
        )
        gravity_force = _clamp(
            global_market.macro_liquidity.funding_pressure * 0.55
            + global_market.macro_liquidity.policy_tightness * 0.45,
            0.0,
            1.0,
        )
        gravity = FundingGravity(
            force=gravity_force,
            direction="downward" if gravity_force >= 0.55 else "neutral",
            confidence=_clamp(global_market.macro_liquidity.confidence, 0.0, 1.0),
        )
        net_energy = _clamp(momentum.score - friction.drag - turbulence.intensity * 0.40 - gravity.force * 0.25, -1.0, 1.0)
        energy_balance = _clamp(momentum.score - friction.coefficient, -1.0, 1.0)
        instability_score = _clamp(
            friction.coefficient * 0.30
            + turbulence.shock_probability * 0.45
            + gravity.force * 0.25,
            0.0,
            1.0,
        )
        reasons: list[str] = []
        if turbulence.shock_probability >= 0.70:
            reasons.append("turbulence_shock_risk_high")
        if friction.coefficient >= 0.65:
            reasons.append("liquidity_friction_high")
        if gravity.force >= 0.65:
            reasons.append("funding_gravity_heavy")
        instability = EnergyInstabilitySignal(
            instability_score=instability_score,
            unstable=bool(instability_score >= 0.65),
            reason_codes=tuple(reasons),
        )
        return MarketEnergyState(
            momentum=momentum,
            friction=friction,
            turbulence=turbulence,
            gravity=gravity,
            net_energy=net_energy,
            energy_balance=energy_balance,
            instability=instability,
            diagnostics={
                "phase": 28,
                "energy_regime": "explosive" if net_energy >= 0.50 else "fragile" if instability_score >= 0.65 else "balanced",
            },
        )
