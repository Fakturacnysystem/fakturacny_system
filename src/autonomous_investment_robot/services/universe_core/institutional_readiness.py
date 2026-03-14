from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping

from .autonomous_fund_brain import FundBrainRecommendation
from .capital_survival_doctrine import SurvivalDoctrineDecision


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeploymentCertification:
    certificate_id: str
    approved: bool
    stage: str
    checklist: list[dict[str, Any]] = field(default_factory=list)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "certificate_id": self.certificate_id,
            "approved": bool(self.approved),
            "stage": self.stage,
            "checklist": [dict(row) for row in self.checklist],
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class TruthRoomIndex:
    index_id: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_id": self.index_id,
            "artifacts": [dict(row) for row in self.artifacts],
        }


@dataclass(frozen=True)
class ValuationEvidencePack:
    pack_id: str
    expected_return_score: float
    risk_adjusted_score: float
    confidence: float
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "expected_return_score": float(self.expected_return_score),
            "risk_adjusted_score": float(self.risk_adjusted_score),
            "confidence": float(self.confidence),
            "assumptions": [str(item) for item in self.assumptions],
        }


@dataclass(frozen=True)
class OperatorDossier:
    dossier_id: str
    required_controls: list[str] = field(default_factory=list)
    runbooks: list[str] = field(default_factory=list)
    decision_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dossier_id": self.dossier_id,
            "required_controls": [str(item) for item in self.required_controls],
            "runbooks": [str(item) for item in self.runbooks],
            "decision_summary": dict(self.decision_summary),
        }


@dataclass(frozen=True)
class ResidualRiskRegister:
    register_id: str
    risks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "register_id": self.register_id,
            "risks": [dict(row) for row in self.risks],
        }


@dataclass(frozen=True)
class InstitutionalReadinessReport:
    report_id: str
    readiness_score: float
    approved: bool
    deployment_certification: DeploymentCertification
    truth_room: TruthRoomIndex
    valuation_evidence: ValuationEvidencePack
    operator_dossier: OperatorDossier
    residual_risks: ResidualRiskRegister
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "readiness_score": float(self.readiness_score),
            "approved": bool(self.approved),
            "deployment_certification": self.deployment_certification.to_dict(),
            "truth_room": self.truth_room.to_dict(),
            "valuation_evidence": self.valuation_evidence.to_dict(),
            "operator_dossier": self.operator_dossier.to_dict(),
            "residual_risks": self.residual_risks.to_dict(),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


class InstitutionalReadinessEngine:
    """Phase 35 machine-readable institutional readiness compiler."""

    def compile(
        self,
        *,
        cycle_id: str,
        ops_snapshot: Mapping[str, Any],
        fund_recommendation: FundBrainRecommendation,
        survival: SurvivalDoctrineDecision,
    ) -> InstitutionalReadinessReport:
        stage = str(ops_snapshot.get("rollout_stage", "blocked") or "blocked")
        blockers = [str(item) for item in ops_snapshot.get("blockers", [])] if isinstance(ops_snapshot.get("blockers", []), list) else []
        checklist = [
            {"item_id": "ops_rollout_not_blocked", "passed": stage != "blocked", "required": True},
            {"item_id": "fund_recommendation_approved", "passed": bool(fund_recommendation.approved), "required": True},
            {"item_id": "survival_veto_clear", "passed": not bool(survival.safety_veto), "required": True},
            {"item_id": "manual_gate_required_flag_visible", "passed": "manual_gate_required" in ops_snapshot, "required": True},
        ]
        cert_approved = all(bool(row.get("passed", False) or not bool(row.get("required", False))) for row in checklist)
        cert = DeploymentCertification(
            certificate_id=_stable_hash({"phase": 35, "cycle_id": cycle_id, "stage": stage})[:16],
            approved=cert_approved,
            stage=stage,
            checklist=checklist,
            reason_codes=tuple([] if cert_approved else ["deployment_requirements_not_met"]),
        )
        ops_artifact_id = _stable_hash(
            {
                "phase": 35,
                "cycle_id": cycle_id,
                "ops_snapshot": dict(ops_snapshot),
            }
        )[:16]
        truth_room = TruthRoomIndex(
            index_id=_stable_hash({"phase": 35, "cycle_id": cycle_id, "truth_room": 1})[:16],
            artifacts=[
                {"artifact_type": "ops_snapshot", "artifact_id": ops_artifact_id, "source": "runtime"},
                {"artifact_type": "fund_recommendation", "artifact_id": fund_recommendation.recommendation_id, "source": "phase34"},
                {"artifact_type": "survival_doctrine", "artifact_id": survival.existential_risk.level, "source": "phase32"},
            ],
        )
        valuation = ValuationEvidencePack(
            pack_id=_stable_hash({"phase": 35, "cycle_id": cycle_id, "valuation": 1})[:16],
            expected_return_score=_clamp(_safe_float(ops_snapshot.get("readiness_score", 0.0), 0.0), 0.0, 1.0),
            risk_adjusted_score=_clamp(1.0 - survival.existential_risk.score, 0.0, 1.0),
            confidence=_clamp(
                (_safe_float(ops_snapshot.get("readiness_score", 0.0), 0.0) + (1.0 - survival.existential_risk.score)) / 2.0,
                0.0,
                1.0,
            ),
            assumptions=[
                "readiness_score_is_advisory_only",
                "no_authority_path_replacement",
                "manual_live_gate_and_safety_veto_still_required",
            ],
        )
        dossier = OperatorDossier(
            dossier_id=_stable_hash({"phase": 35, "cycle_id": cycle_id, "dossier": 1})[:16],
            required_controls=[
                "manual_live_gate",
                "operator_approval_artifact",
                "rollback_dry_run_validation",
                "safety_veto_monitoring",
            ],
            runbooks=[
                "docs/operator_runbook.md",
                "docs/live_readiness_checklist.md",
                "docs/runbooks/universe_core_phase_operator_runbook.md",
            ],
            decision_summary={
                "fund_mode": fund_recommendation.mode,
                "survival_mode": survival.recommendation_mode,
                "rollout_stage": stage,
            },
        )
        risk_rows: list[dict[str, Any]] = [
            {"risk": "survival_veto", "severity": survival.existential_risk.level, "active": bool(survival.safety_veto)},
            {"risk": "ops_blockers", "severity": "high" if blockers else "low", "active": bool(blockers), "blockers": blockers},
            {
                "risk": "committee_disagreement",
                "severity": "high" if bool(getattr(getattr(fund_recommendation.bundle, "disagreement_map", None), "vetoes", [])) else "medium" if fund_recommendation.bundle and fund_recommendation.bundle.disagreement_map.disagreements else "low",
                "active": bool(fund_recommendation.bundle and fund_recommendation.bundle.disagreement_map.disagreements),
            },
        ]
        residual = ResidualRiskRegister(
            register_id=_stable_hash({"phase": 35, "cycle_id": cycle_id, "residual": 1})[:16],
            risks=risk_rows,
        )
        readiness = _clamp(
            _safe_float(ops_snapshot.get("readiness_score", 0.0), 0.0) * 0.45
            + valuation.risk_adjusted_score * 0.30
            + (1.0 if fund_recommendation.approved else 0.0) * 0.25,
            0.0,
            1.0,
        )
        approved = bool(cert.approved and readiness >= 0.55)
        reasons: list[str] = []
        if not cert.approved:
            reasons.append("certification_failed")
        if readiness < 0.55:
            reasons.append("readiness_score_below_threshold")
        return InstitutionalReadinessReport(
            report_id=_stable_hash({"phase": 35, "cycle_id": cycle_id, "approved": approved})[:16],
            readiness_score=readiness,
            approved=approved,
            deployment_certification=cert,
            truth_room=truth_room,
            valuation_evidence=valuation,
            operator_dossier=dossier,
            residual_risks=residual,
            reason_codes=tuple(reasons),
        )
