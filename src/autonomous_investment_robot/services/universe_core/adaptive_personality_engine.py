from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .cross_reality_signal import CrossRealitySignal
from .market_energy_physics import MarketEnergyState
from .multi_horizon_decision import HorizonAlignmentReport


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


class ExecutionPersonality(str, Enum):
    AGGRESSIVE = "aggressive"
    PATIENT = "patient"
    DEFENSIVE = "defensive"
    PREDATOR = "predator"
    RECOVERY = "recovery"
    SURVIVAL = "survival"


class RiskPersonality(str, Enum):
    AGGRESSIVE = "aggressive"
    PATIENT = "patient"
    DEFENSIVE = "defensive"
    PREDATOR = "predator"
    RECOVERY = "recovery"
    SURVIVAL = "survival"


@dataclass(frozen=True)
class PersonalityConstraints:
    max_size_scale: float
    risk_budget_scale: float
    allow_new_risk: bool
    hard_safety_override: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_size_scale": float(self.max_size_scale),
            "risk_budget_scale": float(self.risk_budget_scale),
            "allow_new_risk": bool(self.allow_new_risk),
            "hard_safety_override": bool(self.hard_safety_override),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class PersonalityShiftDecision:
    previous_execution: ExecutionPersonality
    previous_risk: RiskPersonality
    next_execution: ExecutionPersonality
    next_risk: RiskPersonality
    shifted: bool
    hysteresis_hold_steps: int
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_execution": self.previous_execution.value,
            "previous_risk": self.previous_risk.value,
            "next_execution": self.next_execution.value,
            "next_risk": self.next_risk.value,
            "shifted": bool(self.shifted),
            "hysteresis_hold_steps": int(self.hysteresis_hold_steps),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class PersonalityTrace:
    cycle_id: str
    execution_personality: ExecutionPersonality
    risk_personality: RiskPersonality
    shift: PersonalityShiftDecision
    constraints: PersonalityConstraints
    as_of_ts: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "execution_personality": self.execution_personality.value,
            "risk_personality": self.risk_personality.value,
            "shift": self.shift.to_dict(),
            "constraints": self.constraints.to_dict(),
            "as_of_ts": float(self.as_of_ts),
        }


class AdaptivePersonalityEngine:
    """Phase 31 deterministic personality state machine with hysteresis."""

    def __init__(self, *, hysteresis_steps: int = 2) -> None:
        self.hysteresis_steps = max(1, int(hysteresis_steps))
        self._execution = ExecutionPersonality.PATIENT
        self._risk = RiskPersonality.PATIENT
        self._candidate: tuple[ExecutionPersonality, RiskPersonality] | None = None
        self._candidate_steps = 0

    def assess(
        self,
        *,
        cycle_id: str,
        as_of_ts: float,
        horizon: HorizonAlignmentReport,
        energy: MarketEnergyState,
        cross_reality: CrossRealitySignal,
        safety_hard_stop: bool,
    ) -> PersonalityTrace:
        target_execution = self._execution
        target_risk = self._risk
        reasons: list[str] = []
        stress = _clamp(
            energy.instability.instability_score * 0.45
            + cross_reality.composite_pressure * 0.35
            + (1.0 - horizon.alignment_score) * 0.20,
            0.0,
            1.0,
        )
        if safety_hard_stop or stress >= 0.80:
            target_execution = ExecutionPersonality.SURVIVAL
            target_risk = RiskPersonality.SURVIVAL
            reasons.append("stress_extreme")
        elif stress >= 0.65:
            target_execution = ExecutionPersonality.DEFENSIVE
            target_risk = RiskPersonality.DEFENSIVE
            reasons.append("stress_high")
        elif horizon.tactical.opportunity_score >= 0.72 and energy.net_energy > 0.20 and cross_reality.composite_pressure < 0.45:
            target_execution = ExecutionPersonality.AGGRESSIVE
            target_risk = RiskPersonality.PREDATOR
            reasons.append("high_opportunity_window")
        elif self._risk in {RiskPersonality.SURVIVAL, RiskPersonality.DEFENSIVE} and stress < 0.50:
            target_execution = ExecutionPersonality.RECOVERY
            target_risk = RiskPersonality.RECOVERY
            reasons.append("post_stress_recovery")
        else:
            target_execution = ExecutionPersonality.PATIENT
            target_risk = RiskPersonality.PATIENT
            reasons.append("baseline_patient")

        previous_execution = self._execution
        previous_risk = self._risk
        shifted = False
        hold = 0
        candidate = (target_execution, target_risk)
        if candidate == (self._execution, self._risk):
            self._candidate = None
            self._candidate_steps = 0
        else:
            if self._candidate == candidate:
                self._candidate_steps += 1
            else:
                self._candidate = candidate
                self._candidate_steps = 1
            hold = max(0, self.hysteresis_steps - self._candidate_steps)
            if self._candidate_steps >= self.hysteresis_steps or target_execution == ExecutionPersonality.SURVIVAL:
                self._execution, self._risk = candidate
                shifted = True
                self._candidate = None
                self._candidate_steps = 0
            else:
                target_execution = self._execution
                target_risk = self._risk

        constraints = self._constraints_for(
            execution=self._execution,
            risk=self._risk,
            safety_hard_stop=safety_hard_stop,
        )
        shift = PersonalityShiftDecision(
            previous_execution=previous_execution,
            previous_risk=previous_risk,
            next_execution=self._execution,
            next_risk=self._risk,
            shifted=shifted,
            hysteresis_hold_steps=hold,
            reason_codes=tuple(reasons),
        )
        return PersonalityTrace(
            cycle_id=str(cycle_id),
            execution_personality=self._execution,
            risk_personality=self._risk,
            shift=shift,
            constraints=constraints,
            as_of_ts=_safe_float(as_of_ts, 0.0),
        )

    def _constraints_for(
        self,
        *,
        execution: ExecutionPersonality,
        risk: RiskPersonality,
        safety_hard_stop: bool,
    ) -> PersonalityConstraints:
        if safety_hard_stop or risk == RiskPersonality.SURVIVAL:
            return PersonalityConstraints(
                max_size_scale=0.0,
                risk_budget_scale=0.0,
                allow_new_risk=False,
                hard_safety_override=True,
                reason_codes=("hard_stop_enforced",),
            )
        if risk == RiskPersonality.DEFENSIVE:
            return PersonalityConstraints(
                max_size_scale=0.35,
                risk_budget_scale=0.30,
                allow_new_risk=False,
                hard_safety_override=False,
                reason_codes=("defensive_constraints",),
            )
        if risk == RiskPersonality.RECOVERY:
            return PersonalityConstraints(
                max_size_scale=0.55,
                risk_budget_scale=0.50,
                allow_new_risk=False,
                hard_safety_override=False,
                reason_codes=("recovery_constraints",),
            )
        if execution == ExecutionPersonality.AGGRESSIVE:
            return PersonalityConstraints(
                max_size_scale=0.85,
                risk_budget_scale=0.75,
                allow_new_risk=True,
                hard_safety_override=False,
                reason_codes=("aggressive_window",),
            )
        return PersonalityConstraints(
            max_size_scale=0.65,
            risk_budget_scale=0.60,
            allow_new_risk=True,
            hard_safety_override=False,
            reason_codes=("patient_default",),
        )
