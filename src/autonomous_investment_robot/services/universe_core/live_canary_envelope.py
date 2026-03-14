from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CanaryBlocker:
    blocker_id: str
    source: str
    severity: str
    message: str
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocker_id": self.blocker_id,
            "source": self.source,
            "severity": self.severity,
            "message": self.message,
            "active": bool(self.active),
        }


@dataclass(frozen=True)
class CanaryGovernanceEnvelope:
    envelope_id: str
    deterministic: bool
    canary_allowed: bool
    manual_gate_lock: bool
    resolved_stage: str
    checklist: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    blockers: tuple[CanaryBlocker, ...] = field(default_factory=tuple)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "deterministic": bool(self.deterministic),
            "canary_allowed": bool(self.canary_allowed),
            "manual_gate_lock": bool(self.manual_gate_lock),
            "resolved_stage": self.resolved_stage,
            "checklist": [dict(row) for row in self.checklist],
            "blockers": [row.to_dict() for row in self.blockers],
            "reason_codes": [str(item) for item in self.reason_codes],
        }


class LiveCanaryEnvelopeCompiler:
    """Phase 49 deterministic canary-governance envelope compiler."""

    def compile(
        self,
        *,
        rollout_stage: str,
        manual_gate_required: bool,
        manual_gate_present: bool,
        safety_veto: bool,
        evidence_ready: bool,
        deployment_gate_open: bool,
    ) -> CanaryGovernanceEnvelope:
        checklist = (
            {"item_id": "manual_gate_present", "required": bool(manual_gate_required), "passed": bool(manual_gate_present)},
            {"item_id": "safety_veto_clear", "required": True, "passed": not bool(safety_veto)},
            {"item_id": "evidence_index_ready", "required": True, "passed": bool(evidence_ready)},
            {"item_id": "deployment_gate_open", "required": True, "passed": bool(deployment_gate_open)},
        )
        blockers: list[CanaryBlocker] = []
        reason_codes: list[str] = []
        if manual_gate_required and not manual_gate_present:
            blockers.append(
                CanaryBlocker(
                    blocker_id="manual_gate_lock",
                    source="manual_gate",
                    severity="critical",
                    message="manual live gate is not satisfied",
                )
            )
            reason_codes.append("manual_gate_lock_active")
        if safety_veto:
            blockers.append(
                CanaryBlocker(
                    blocker_id="safety_veto",
                    source="committee_or_survival",
                    severity="critical",
                    message="safety veto active",
                )
            )
            reason_codes.append("safety_veto_active")
        if not evidence_ready:
            blockers.append(
                CanaryBlocker(
                    blocker_id="missing_evidence",
                    source="phase48",
                    severity="high",
                    message="required evidence index is not ready",
                )
            )
            reason_codes.append("evidence_not_ready")
        if not deployment_gate_open:
            blockers.append(
                CanaryBlocker(
                    blocker_id="deployment_gate_blocked",
                    source="phase43",
                    severity="high",
                    message="deployment gate not open for canary",
                )
            )
            reason_codes.append("deployment_gate_blocked")

        canary_allowed = len(blockers) == 0
        manual_gate_lock = bool(manual_gate_required and not manual_gate_present)
        resolved_stage = "canary_ready" if canary_allowed else "blocked"
        if canary_allowed:
            reason_codes.append("canary_ready")
        envelope_id = _stable_hash(
            {
                "phase": 49,
                "rollout_stage": str(rollout_stage),
                "manual_gate_required": bool(manual_gate_required),
                "manual_gate_present": bool(manual_gate_present),
                "safety_veto": bool(safety_veto),
                "evidence_ready": bool(evidence_ready),
                "deployment_gate_open": bool(deployment_gate_open),
                "resolved_stage": resolved_stage,
            }
        )[:24]
        return CanaryGovernanceEnvelope(
            envelope_id=envelope_id,
            deterministic=True,
            canary_allowed=canary_allowed,
            manual_gate_lock=manual_gate_lock,
            resolved_stage=resolved_stage,
            checklist=checklist,
            blockers=tuple(blockers),
            reason_codes=tuple(dict.fromkeys(reason_codes)),
        )
