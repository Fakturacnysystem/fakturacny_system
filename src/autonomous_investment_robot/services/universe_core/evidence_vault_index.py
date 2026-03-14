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
class ReplayAuditPointer:
    pointer_id: str
    pointer_type: str
    artifact_id: str
    required: bool
    present: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pointer_id": self.pointer_id,
            "pointer_type": self.pointer_type,
            "artifact_id": self.artifact_id,
            "required": bool(self.required),
            "present": bool(self.present),
            "reason_codes": [str(item) for item in self.reason_codes],
        }


@dataclass(frozen=True)
class EvidenceLedgerIndex:
    index_id: str
    deterministic: bool
    bounded: bool
    ready: bool
    pointers: tuple[ReplayAuditPointer, ...] = field(default_factory=tuple)
    missing_required_artifacts: tuple[str, ...] = field(default_factory=tuple)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_id": self.index_id,
            "deterministic": bool(self.deterministic),
            "bounded": bool(self.bounded),
            "ready": bool(self.ready),
            "pointers": [row.to_dict() for row in self.pointers],
            "missing_required_artifacts": [str(item) for item in self.missing_required_artifacts],
            "reason_codes": [str(item) for item in self.reason_codes],
        }


class EvidenceVaultIndexBuilder:
    """Phase 48 deterministic evidence index compiler for audit replay linkage."""

    REQUIRED_POINTERS: tuple[tuple[str, str], ...] = (
        ("decision_packet", "cycle_id"),
        ("phase36_ledger", "ledger_id"),
        ("phase45_ensemble", "ensemble_id"),
        ("phase47_distributed_contract", "contract_id"),
        ("phase42_escalation_ticket", "ticket_id"),
        ("phase43_deployment_gate", "contract_id"),
    )

    def build(
        self,
        *,
        packet: Mapping[str, Any] | None,
        ops_snapshot: Mapping[str, Any] | None,
        advanced_intelligence: Mapping[str, Any] | None,
    ) -> EvidenceLedgerIndex:
        pkt = _safe_mapping(packet)
        ops = _safe_mapping(ops_snapshot)
        intel = _safe_mapping(advanced_intelligence)
        sources: dict[str, Mapping[str, Any]] = {
            "decision_packet": pkt,
            "phase36_ledger": _safe_mapping(intel.get("phase36_intelligence_ledger", {})),
            "phase45_ensemble": _safe_mapping(intel.get("phase45_future_simulation_ensemble", {})),
            "phase47_distributed_contract": _safe_mapping(intel.get("phase47_replay_distributed_bridge", {})),
            "phase42_escalation_ticket": _safe_mapping(intel.get("phase42_committee_escalation", {})),
            "phase43_deployment_gate": _safe_mapping(intel.get("phase43_institutional_gate", {})),
            "phase10_rollout_governance": _safe_mapping(ops.get("rollout_governance", {})),
            "phase10_production_readiness": _safe_mapping(ops.get("production_readiness", {})),
        }
        pointers: list[ReplayAuditPointer] = []
        missing_required: list[str] = []
        for pointer_type, artifact_key in self.REQUIRED_POINTERS:
            src = _safe_mapping(sources.get(pointer_type, {}))
            artifact_id = str(src.get(artifact_key, "") or "")
            present = bool(artifact_id)
            reason_codes = ("artifact_missing",) if not present else ("artifact_linked",)
            pointers.append(
                ReplayAuditPointer(
                    pointer_id=_stable_hash(
                        {
                            "phase": 48,
                            "pointer_type": pointer_type,
                            "artifact_key": artifact_key,
                            "artifact_id": artifact_id,
                        }
                    )[:24],
                    pointer_type=pointer_type,
                    artifact_id=artifact_id,
                    required=True,
                    present=present,
                    reason_codes=reason_codes,
                )
            )
            if not present:
                missing_required.append(pointer_type)
        for pointer_type, artifact_key in (
            ("phase10_rollout_governance", "decision"),
            ("phase10_production_readiness", "artifact_id"),
        ):
            src = _safe_mapping(sources.get(pointer_type, {}))
            artifact = src.get(artifact_key)
            artifact_id = str(_safe_mapping(artifact).get("decision_id", "") or artifact or "")
            present = bool(artifact_id)
            pointers.append(
                ReplayAuditPointer(
                    pointer_id=_stable_hash(
                        {
                            "phase": 48,
                            "pointer_type": pointer_type,
                            "artifact_key": artifact_key,
                            "artifact_id": artifact_id,
                        }
                    )[:24],
                    pointer_type=pointer_type,
                    artifact_id=artifact_id,
                    required=False,
                    present=present,
                    reason_codes=("artifact_linked",) if present else ("artifact_optional_missing",),
                )
            )
        ready = len(missing_required) == 0
        reason_codes = ["evidence_index_ready"] if ready else ["missing_required_evidence_links"]
        index_id = _stable_hash(
            {
                "phase": 48,
                "ready": bool(ready),
                "missing_required": sorted(missing_required),
                "pointer_ids": [row.pointer_id for row in pointers],
            }
        )[:24]
        return EvidenceLedgerIndex(
            index_id=index_id,
            deterministic=True,
            bounded=True,
            ready=ready,
            pointers=tuple(pointers),
            missing_required_artifacts=tuple(sorted(missing_required)),
            reason_codes=tuple(reason_codes),
        )
