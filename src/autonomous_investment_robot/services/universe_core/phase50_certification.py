from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResidualRiskTruthTable:
    rows: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    unresolved_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [dict(row) for row in self.rows],
            "unresolved_count": int(self.unresolved_count),
        }


@dataclass(frozen=True)
class AutonomousCapitalCertification:
    certificate_id: str
    deterministic: bool
    reproducible: bool
    approved: bool
    readiness_stage: str
    recommended_next_phase: int | None
    residual_risk_truth_table: ResidualRiskTruthTable
    rollback_controls: dict[str, Any] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    generated_from: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "deterministic": bool(self.deterministic),
            "reproducible": bool(self.reproducible),
            "approved": bool(self.approved),
            "readiness_stage": self.readiness_stage,
            "recommended_next_phase": self.recommended_next_phase,
            "residual_risk_truth_table": self.residual_risk_truth_table.to_dict(),
            "rollback_controls": dict(self.rollback_controls),
            "reason_codes": [str(item) for item in self.reason_codes],
            "generated_from": dict(self.generated_from),
        }


class Phase50CertificationCompiler:
    """Phase 50 deterministic institutional autonomous-capital certification compiler."""

    REQUIRED_PHASES: tuple[int, ...] = tuple(range(36, 51))

    def compile(
        self,
        *,
        advanced_intelligence: Mapping[str, Any] | None,
        ops_snapshot: Mapping[str, Any] | None,
        completed_phases: list[int],
    ) -> AutonomousCapitalCertification:
        intel = _safe_mapping(advanced_intelligence)
        ops = _safe_mapping(ops_snapshot)
        phase35 = _safe_mapping(intel.get("phase35_institutional_readiness", {}))
        phase49 = _safe_mapping(intel.get("phase49_live_canary_envelope", {}))
        phase48 = _safe_mapping(intel.get("phase48_evidence_vault_index", {}))
        phase43 = _safe_mapping(intel.get("phase43_institutional_gate", {}))
        rollout = _safe_mapping(ops.get("rollout_governance", {}))
        rollback = _safe_mapping(rollout.get("rollback_readiness", {}))
        risk_rows: list[dict[str, Any]] = []
        readiness_approved = bool(phase35.get("approved", False))
        risk_rows.append(
            {
                "risk_id": "institutional_readiness",
                "active": not readiness_approved,
                "severity": "high" if not readiness_approved else "low",
                "evidence": "phase35_institutional_readiness.approved",
            }
        )
        canary_allowed = bool(phase49.get("canary_allowed", False))
        risk_rows.append(
            {
                "risk_id": "canary_governance",
                "active": not canary_allowed,
                "severity": "critical" if not canary_allowed else "low",
                "evidence": "phase49_live_canary_envelope.canary_allowed",
            }
        )
        evidence_ready = bool(phase48.get("ready", False))
        risk_rows.append(
            {
                "risk_id": "evidence_integrity",
                "active": not evidence_ready,
                "severity": "high" if not evidence_ready else "low",
                "evidence": "phase48_evidence_vault_index.ready",
            }
        )
        gate_open = bool(phase43.get("gate_open", False))
        risk_rows.append(
            {
                "risk_id": "deployment_gate",
                "active": not gate_open,
                "severity": "high" if not gate_open else "low",
                "evidence": "phase43_institutional_gate.gate_open",
            }
        )
        rollback_ready = bool(rollback.get("rollback_ready", False) and rollback.get("dry_run_validated", False))
        risk_rows.append(
            {
                "risk_id": "rollback_controls",
                "active": not rollback_ready,
                "severity": "critical" if not rollback_ready else "low",
                "evidence": "rollout_governance.rollback_readiness",
            }
        )
        unresolved = [row for row in risk_rows if bool(row.get("active", False))]
        table = ResidualRiskTruthTable(
            rows=tuple(risk_rows),
            unresolved_count=len(unresolved),
        )
        all_phases_complete = sorted(set(int(item) for item in completed_phases)) == list(self.REQUIRED_PHASES)
        recommended_next_phase: int | None = None if all_phases_complete else 50
        readiness_stage = str(ops.get("rollout_stage", "blocked") or "blocked")
        approved = bool((len(unresolved) == 0) and all_phases_complete and readiness_stage != "blocked")
        reason_codes: list[str] = []
        if not all_phases_complete:
            reason_codes.append("window_36_50_not_fully_complete")
        if unresolved:
            reason_codes.append("residual_risks_unresolved")
        if not rollback_ready:
            reason_codes.append("rollback_controls_incomplete")
        if not reason_codes:
            reason_codes.append("phase50_certification_ready")
        generated_from = {
            "phase35_report_id": str(phase35.get("report_id", "")),
            "phase48_index_id": str(phase48.get("index_id", "")),
            "phase49_envelope_id": str(phase49.get("envelope_id", "")),
            "rollout_stage": readiness_stage,
            "completed_phases": sorted(set(int(item) for item in completed_phases)),
        }
        certificate_id = _stable_hash(
            {
                "phase": 50,
                "approved": bool(approved),
                "readiness_stage": readiness_stage,
                "unresolved_count": len(unresolved),
                "recommended_next_phase": recommended_next_phase,
                "completed_phases": generated_from["completed_phases"],
                "reason_codes": sorted(set(reason_codes)),
            }
        )[:24]
        return AutonomousCapitalCertification(
            certificate_id=certificate_id,
            deterministic=True,
            reproducible=True,
            approved=approved,
            readiness_stage=readiness_stage,
            recommended_next_phase=recommended_next_phase,
            residual_risk_truth_table=table,
            rollback_controls=rollback,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            generated_from=generated_from,
        )
