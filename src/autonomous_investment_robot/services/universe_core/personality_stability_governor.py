from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .adaptive_personality_engine import (
    ExecutionPersonality,
    PersonalityConstraints,
    PersonalityShiftDecision,
    PersonalityTrace,
    RiskPersonality,
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass(frozen=True)
class PersonalityTransitionBudget:
    window_size: int
    max_transitions: int
    transitions_used: int
    transitions_remaining: int
    deterministic: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_size": int(self.window_size),
            "max_transitions": int(self.max_transitions),
            "transitions_used": int(self.transitions_used),
            "transitions_remaining": int(self.transitions_remaining),
            "deterministic": bool(self.deterministic),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class StabilityViolation:
    violation_code: str
    severity: str
    blocked_transition: bool
    recommended_execution: str
    recommended_risk: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_code": self.violation_code,
            "severity": self.severity,
            "blocked_transition": bool(self.blocked_transition),
            "recommended_execution": self.recommended_execution,
            "recommended_risk": self.recommended_risk,
            "reason_codes": [str(item) for item in self.reason_codes],
        }


class PersonalityStabilityGovernor:
    """Phase 41 bounded transition-governor over personality state shifts."""

    def __init__(self, *, window_size: int = 6, max_transitions: int = 2) -> None:
        self.window_size = max(2, int(window_size))
        self.max_transitions = max(1, int(max_transitions))
        self._transition_history: list[bool] = []

    def enforce(
        self,
        *,
        trace: PersonalityTrace,
        safety_hard_stop: bool,
    ) -> tuple[PersonalityTrace, PersonalityTransitionBudget, StabilityViolation | None]:
        shifted = bool(trace.shift.shifted)
        if safety_hard_stop or trace.constraints.hard_safety_override:
            self._append_transition(shifted)
            budget = self._build_budget(reason_codes=("hard_safety_override",))
            return trace, budget, None

        transitions_used = sum(1 for item in self._transition_history if item)
        would_exceed = bool(shifted and transitions_used >= self.max_transitions)
        if would_exceed:
            conservative_constraints = PersonalityConstraints(
                max_size_scale=min(0.50, float(trace.constraints.max_size_scale)),
                risk_budget_scale=min(0.45, float(trace.constraints.risk_budget_scale)),
                allow_new_risk=False,
                hard_safety_override=False,
                reason_codes=tuple(list(trace.constraints.reason_codes) + ["phase41_transition_budget_enforced"]),
            )
            constrained_shift = PersonalityShiftDecision(
                previous_execution=trace.shift.previous_execution,
                previous_risk=trace.shift.previous_risk,
                next_execution=trace.shift.previous_execution,
                next_risk=trace.shift.previous_risk,
                shifted=False,
                hysteresis_hold_steps=int(trace.shift.hysteresis_hold_steps) + 1,
                reason_codes=tuple(list(trace.shift.reason_codes) + ["phase41_transition_budget_blocked"]),
            )
            constrained = replace(
                trace,
                execution_personality=trace.shift.previous_execution,
                risk_personality=trace.shift.previous_risk,
                shift=constrained_shift,
                constraints=conservative_constraints,
            )
            violation = StabilityViolation(
                violation_code="phase41_transition_budget_exceeded",
                severity="high",
                blocked_transition=True,
                recommended_execution=trace.shift.previous_execution.value,
                recommended_risk=trace.shift.previous_risk.value,
                reason_codes=("phase41_transition_budget_exceeded",),
            )
            self._append_transition(False)
            budget = self._build_budget(reason_codes=("phase41_transition_budget_exceeded",))
            return constrained, budget, violation

        self._append_transition(shifted)
        budget = self._build_budget(reason_codes=("phase41_transition_within_budget",))
        return trace, budget, None

    def _append_transition(self, shifted: bool) -> None:
        self._transition_history.append(bool(shifted))
        if len(self._transition_history) > self.window_size:
            self._transition_history = self._transition_history[-self.window_size :]

    def _build_budget(self, *, reason_codes: tuple[str, ...]) -> PersonalityTransitionBudget:
        transitions_used = sum(1 for item in self._transition_history if item)
        remaining = max(0, self.max_transitions - transitions_used)
        return PersonalityTransitionBudget(
            window_size=self.window_size,
            max_transitions=self.max_transitions,
            transitions_used=transitions_used,
            transitions_remaining=remaining,
            deterministic=True,
            reason_codes=reason_codes,
        )
