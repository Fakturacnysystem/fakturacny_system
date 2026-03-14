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


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VetoRationaleBundle:
    bundle_id: str
    safety_veto: bool
    veto_sources: tuple[str, ...] = field(default_factory=tuple)
    rationale_items: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    machine_readable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "safety_veto": bool(self.safety_veto),
            "veto_sources": [str(item) for item in self.veto_sources],
            "rationale_items": [dict(item) for item in self.rationale_items],
            "machine_readable": bool(self.machine_readable),
        }


@dataclass(frozen=True)
class EscalationTicket:
    ticket_id: str
    level: str
    deterministic: bool
    requires_operator_ack: bool
    disagreement_severity: float
    safety_veto: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    committee_votes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    veto_bundle: VetoRationaleBundle | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "level": self.level,
            "deterministic": bool(self.deterministic),
            "requires_operator_ack": bool(self.requires_operator_ack),
            "disagreement_severity": float(self.disagreement_severity),
            "safety_veto": bool(self.safety_veto),
            "reason_codes": [str(item) for item in self.reason_codes],
            "committee_votes": [dict(row) for row in self.committee_votes],
            "veto_bundle": self.veto_bundle.to_dict() if self.veto_bundle is not None else None,
        }


class CommitteeEscalationProtocol:
    """Phase 42 deterministic committee escalation and veto rationale compiler."""

    def compile(
        self,
        *,
        cycle_id: str,
        fund_recommendation: Mapping[str, Any] | None,
        survival_doctrine: Mapping[str, Any] | None,
    ) -> EscalationTicket:
        fund = _safe_mapping(fund_recommendation)
        survival = _safe_mapping(survival_doctrine)
        bundle = _safe_mapping(fund.get("bundle", {}))
        disagreement = _safe_mapping(bundle.get("disagreement_map", {}))
        severity = max(0.0, min(1.0, _safe_float(disagreement.get("severity", 0.0), 0.0)))
        committee_votes: list[dict[str, Any]] = []
        for key in ("research_vote", "risk_vote", "execution_vote", "portfolio_vote"):
            vote = _safe_mapping(bundle.get(key, {}))
            if vote:
                committee_votes.append(
                    {
                        "committee": str(vote.get("committee", key.replace("_vote", ""))),
                        "vote": str(vote.get("vote", "")),
                        "confidence": _safe_float(vote.get("confidence", 0.0), 0.0),
                        "reason_codes": [str(item) for item in vote.get("reason_codes", []) if str(item)]
                        if isinstance(vote.get("reason_codes", []), list)
                        else [],
                    }
                )
        safety_veto = bool(survival.get("safety_veto", False) or bundle.get("safety_veto", False))
        veto_sources: list[str] = []
        if bool(survival.get("safety_veto", False)):
            veto_sources.append("phase32_survival_doctrine")
        if bool(bundle.get("safety_veto", False)):
            veto_sources.append("phase34_committee_bundle")
        veto_bundle = VetoRationaleBundle(
            bundle_id=_stable_hash(
                {
                    "phase": 42,
                    "cycle_id": cycle_id,
                    "safety_veto": bool(safety_veto),
                    "veto_sources": sorted(veto_sources),
                    "severity": round(severity, 6),
                }
            )[:24],
            safety_veto=safety_veto,
            veto_sources=tuple(sorted(veto_sources)),
            rationale_items=tuple(
                {
                    "source": str(source),
                    "reason": "safety_veto_propagated",
                }
                for source in sorted(veto_sources)
            ),
            machine_readable=True,
        )
        level = "critical" if safety_veto else "high" if severity >= 0.65 else "medium" if severity >= 0.35 else "low"
        reason_codes: list[str] = []
        if safety_veto:
            reason_codes.append("safety_veto_propagated")
        if severity >= 0.35:
            reason_codes.append("committee_disagreement_elevated")
        if not reason_codes:
            reason_codes.append("committee_alignment_stable")
        requires_operator_ack = bool(level in {"critical", "high"} or safety_veto)
        ticket_id = _stable_hash(
            {
                "phase": 42,
                "cycle_id": cycle_id,
                "level": level,
                "safety_veto": bool(safety_veto),
                "severity": round(severity, 6),
                "votes": committee_votes,
                "reasons": sorted(set(reason_codes)),
            }
        )[:24]
        return EscalationTicket(
            ticket_id=ticket_id,
            level=level,
            deterministic=True,
            requires_operator_ack=requires_operator_ack,
            disagreement_severity=severity,
            safety_veto=safety_veto,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            committee_votes=tuple(committee_votes),
            veto_bundle=veto_bundle,
        )
