from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class GateBlocker:
    blocker_id: str
    blocker_type: str
    severity: str
    message: str
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocker_id": self.blocker_id,
            "blocker_type": self.blocker_type,
            "severity": self.severity,
            "message": self.message,
            "active": bool(self.active),
        }


@dataclass(frozen=True)
class DeploymentGateContract:
    contract_id: str
    deterministic: bool
    fail_closed: bool
    gate_open: bool
    resolved_stage: str
    manual_gate_required: bool
    manual_gate_present: bool
    safety_veto: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[GateBlocker, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "deterministic": bool(self.deterministic),
            "fail_closed": bool(self.fail_closed),
            "gate_open": bool(self.gate_open),
            "resolved_stage": self.resolved_stage,
            "manual_gate_required": bool(self.manual_gate_required),
            "manual_gate_present": bool(self.manual_gate_present),
            "safety_veto": bool(self.safety_veto),
            "reason_codes": [str(item) for item in self.reason_codes],
            "blockers": [row.to_dict() for row in self.blockers],
        }


class InstitutionalGateCompiler:
    """Phase 43 deterministic deployment gate compiler with fail-closed behavior."""

    def compile(
        self,
        *,
        cycle_id: str,
        institutional_readiness: Mapping[str, Any] | None,
        committee_escalation: Mapping[str, Any] | None,
        manual_gate_override: Mapping[str, Any] | None = None,
    ) -> DeploymentGateContract:
        readiness = _safe_mapping(institutional_readiness)
        escalation = _safe_mapping(committee_escalation)
        blockers: list[GateBlocker] = []
        reason_codes: list[str] = []
        fail_closed = bool((not readiness) or (not escalation))
        if fail_closed:
            reason_codes.append("missing_required_evidence")

        readiness_approved = bool(readiness.get("approved", False))
        cert = _safe_mapping(readiness.get("deployment_certification", {}))
        readiness_stage = str(cert.get("stage", "blocked") or "blocked")
        safety_veto = bool(escalation.get("safety_veto", False))
        if safety_veto:
            reason_codes.append("safety_veto_active")
            blockers.append(
                GateBlocker(
                    blocker_id="safety_veto",
                    blocker_type="safety",
                    severity="critical",
                    message="committee/survival safety veto is active",
                    active=True,
                )
            )
        if not readiness_approved:
            reason_codes.append("institutional_readiness_not_approved")
            blockers.append(
                GateBlocker(
                    blocker_id="institutional_readiness",
                    blocker_type="readiness",
                    severity="high",
                    message="institutional readiness report is not approved",
                    active=True,
                )
            )
        manual_gate_required = True
        gate_override = _safe_mapping(manual_gate_override)
        if gate_override:
            manual_gate_present = bool(gate_override.get("live_go", False) and gate_override.get("confirmation_file_exists", False))
        else:
            live_go = _truthy(os.getenv("AUTONOMOUS_LIVE_GO"))
            confirmation_file = str(
                os.getenv("AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE", "ops/live_operator_confirmation.txt")
                or "ops/live_operator_confirmation.txt"
            ).strip()
            path = Path(confirmation_file).resolve() if Path(confirmation_file).is_absolute() else (Path.cwd() / confirmation_file).resolve()
            manual_gate_present = bool(live_go and path.exists())
        if manual_gate_required and not manual_gate_present:
            reason_codes.append("manual_live_gate_missing")
            blockers.append(
                GateBlocker(
                    blocker_id="manual_live_gate",
                    blocker_type="governance",
                    severity="critical",
                    message="manual live gate requirements are not satisfied",
                    active=True,
                )
            )

        gate_open = bool((not fail_closed) and readiness_approved and (not safety_veto) and manual_gate_present)
        resolved_stage = readiness_stage if gate_open else "blocked"
        if not gate_open and "deployment_gate_blocked" not in reason_codes:
            reason_codes.append("deployment_gate_blocked")

        contract_id = _stable_hash(
            {
                "phase": 43,
                "cycle_id": cycle_id,
                "fail_closed": bool(fail_closed),
                "gate_open": bool(gate_open),
                "resolved_stage": resolved_stage,
                "manual_gate_present": bool(manual_gate_present),
                "safety_veto": bool(safety_veto),
                "reason_codes": sorted(set(reason_codes)),
                "blocker_ids": [row.blocker_id for row in blockers],
            }
        )[:24]
        return DeploymentGateContract(
            contract_id=contract_id,
            deterministic=True,
            fail_closed=fail_closed,
            gate_open=gate_open,
            resolved_stage=resolved_stage,
            manual_gate_required=manual_gate_required,
            manual_gate_present=manual_gate_present,
            safety_veto=safety_veto,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            blockers=tuple(blockers),
        )
