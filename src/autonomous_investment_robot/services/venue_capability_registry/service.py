from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import CapabilityEvidence, ProviderCapabilityMatrix
from autonomous_investment_robot.services.execution.constraints import provider_capability_matrix


class VenueCapabilityRegistry:
    def __init__(self) -> None:
        self._evidence: dict[str, CapabilityEvidence] = {}

    def _coerce_evidence_dt(self, raw: Any, *, fallback: datetime) -> datetime:
        if isinstance(raw, datetime):
            evidence_dt = raw
        elif isinstance(raw, str):
            try:
                evidence_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except Exception:
                evidence_dt = fallback
        elif isinstance(raw, (int, float)):
            value = float(raw)
            if value > 1e12:
                value /= 1000.0
            try:
                evidence_dt = datetime.fromtimestamp(value, tz=fallback.tzinfo)
            except Exception:
                evidence_dt = fallback
        else:
            evidence_dt = fallback
        if getattr(evidence_dt, "tzinfo", None) is None:
            evidence_dt = evidence_dt.replace(tzinfo=timezone.utc)
        return evidence_dt

    def _inspect(
        self,
        *,
        provider_id: str,
        connector: Any | None = None,
        live: Any | None = None,
        now: datetime | None = None,
    ) -> CapabilityEvidence:
        now_dt = now or datetime.now(timezone.utc)
        integrity = {}
        if live is not None and hasattr(live, "market_integrity_evidence"):
            try:
                integrity = dict(live.market_integrity_evidence(now_dt=now_dt))
            except TypeError:
                integrity = dict(live.market_integrity_evidence())
            except Exception:
                integrity = {}
        capability_payload: dict[str, Any] = {}
        if live is not None and hasattr(live, "capability_evidence"):
            try:
                capability_payload = dict(live.capability_evidence(now_dt=now_dt))
            except TypeError:
                capability_payload = dict(live.capability_evidence())
            except Exception:
                capability_payload = {}
        user_stream_connected = bool(
            capability_payload.get(
                "user_stream_connected",
                getattr(live, "user_stream_connected", getattr(connector, "user_stream_connected", False)),
            )
        )
        lifecycle_snapshot_count = int(capability_payload.get("lifecycle_snapshot_count", 0) or 0)
        lifecycle_snapshot_seeded = bool(capability_payload.get("lifecycle_snapshot_seeded", lifecycle_snapshot_count > 0))
        if lifecycle_snapshot_count <= 0 and live is not None and hasattr(live, "lifecycle_snapshot"):
            try:
                lifecycle_snapshot_count = len(live.lifecycle_snapshot())
            except Exception:
                lifecycle_snapshot_count = 0
        if lifecycle_snapshot_count > 0:
            lifecycle_snapshot_seeded = True
        evidence_ts = integrity.get("ts", now_dt)
        if capability_payload.get("ts") is not None:
            evidence_ts = capability_payload.get("ts")
        evidence_dt = self._coerce_evidence_dt(evidence_ts, fallback=now_dt)
        freshness = max(0.0, (now_dt - evidence_dt).total_seconds())
        sequence_ok = bool(capability_payload.get("sequence_ok", integrity.get("sequence_ok", True)))
        checksum_ok = bool(capability_payload.get("checksum_ok", integrity.get("checksum_ok", True)))
        replace_support_evidence = str(
            capability_payload.get(
                "replace_support_evidence",
                "dynamic" if hasattr(live, "supports_replace") or hasattr(connector, "supports_replace") else "static",
            )
        )
        expire_support_evidence = str(
            capability_payload.get(
                "expire_support_evidence",
                "dynamic" if hasattr(live, "supports_expire") or hasattr(connector, "supports_expire") else "static",
            )
        )
        auth_validated = bool(capability_payload.get("auth_validated", False))
        private_api_healthy = bool(capability_payload.get("private_api_healthy", True))
        public_market_data_connected = bool(capability_payload.get("public_market_data_connected", integrity.get("ts") is not None))
        single_process_scope = bool(capability_payload.get("single_process_scope", False))
        rest_lifecycle_proven = bool(capability_payload.get("rest_lifecycle_proven", False))
        lifecycle_reconciliation_complete = bool(capability_payload.get("lifecycle_reconciliation_complete", False))
        lifecycle_proof_complete = bool(capability_payload.get("lifecycle_proof_complete", False))
        lifecycle_proof_mode = str(capability_payload.get("lifecycle_proof_mode", "") or "")
        ws_lifecycle_observability = bool(capability_payload.get("ws_lifecycle_observability", user_stream_connected and lifecycle_snapshot_seeded))
        payload_classifications = capability_payload.get("classifications", {}) if isinstance(capability_payload.get("classifications"), dict) else {}
        payload_promotion_blockers = [
            str(reason)
            for reason in list(payload_classifications.get("promotion_blocker", []) or [])
            if str(reason) not in {"user_stream_not_connected", "lifecycle_snapshot_absent"}
        ]
        single_process_lifecycle_equivalent = bool(
            provider_id == "kraken_spot"
            and single_process_scope
            and rest_lifecycle_proven
            and lifecycle_reconciliation_complete
            and lifecycle_snapshot_count > 0
            and auth_validated
            and private_api_healthy
            and public_market_data_connected
        )
        reasons: list[str] = []
        partial = False
        if not user_stream_connected and provider_id != "kraken_derivatives" and not single_process_lifecycle_equivalent:
            reasons.append("user_stream_not_connected")
            partial = True
        if not lifecycle_snapshot_seeded:
            reasons.append("lifecycle_snapshot_absent")
            partial = True
        if freshness > 60.0:
            reasons.append("capability_evidence_stale")
            partial = True
        if not sequence_ok:
            reasons.append("sequence_evidence_degraded")
            partial = True
        if not checksum_ok:
            reasons.append("checksum_evidence_degraded")
            partial = True
        if not public_market_data_connected:
            reasons.append("public_market_data_not_connected")
            partial = True
        if not private_api_healthy:
            reasons.append("private_api_health_degraded")
            partial = True
        if bool(capability_payload.get("has_credentials", False)) and not auth_validated and provider_id != "kraken_derivatives":
            reasons.append("auth_validation_unproven")
            partial = True
        for reason in payload_promotion_blockers:
            if reason not in reasons:
                reasons.append(reason)
        classifications = self._classify_reasons(reasons)
        for reason in payload_promotion_blockers:
            if reason not in classifications["promotion_blocker"]:
                classifications["promotion_blocker"].append(reason)
        return CapabilityEvidence(
            provider_id=provider_id,
            ts=now_dt,
            evidence_freshness_seconds=freshness,
            user_stream_connected=user_stream_connected,
            lifecycle_snapshot_count=lifecycle_snapshot_count,
            sequence_ok=sequence_ok,
            checksum_ok=checksum_ok,
            replace_support_evidence=replace_support_evidence,
            expire_support_evidence=expire_support_evidence,
            reasons=reasons,
            partial=partial,
            metadata={
                "supports_live_trading": bool(getattr(connector, "supports_live_trading", getattr(live, "supports_live_trading", False))),
                "auth_validated": auth_validated,
                "private_api_healthy": private_api_healthy,
                "public_market_data_connected": public_market_data_connected,
                "book_repeat_count": int(capability_payload.get("book_repeat_count", 0) or 0),
                "seconds_since_distinct_book_change": float(capability_payload.get("seconds_since_distinct_book_change", 0.0) or 0.0),
                "has_credentials": bool(capability_payload.get("has_credentials", False)),
                "single_process_scope": single_process_scope,
                "rest_lifecycle_proven": rest_lifecycle_proven,
                "lifecycle_reconciliation_complete": lifecycle_reconciliation_complete,
                "lifecycle_proof_complete": lifecycle_proof_complete,
                "lifecycle_proof_mode": lifecycle_proof_mode,
                "single_process_lifecycle_equivalent": single_process_lifecycle_equivalent,
                "ws_lifecycle_observability": ws_lifecycle_observability,
                "lifecycle_snapshot_seeded": lifecycle_snapshot_seeded,
                "classifications": classifications,
            },
        )

    def _classify_reasons(self, reasons: list[str]) -> dict[str, list[str]]:
        classifications = {
            "execution_blocker": [],
            "promotion_blocker": [],
            "confidence_haircut": [],
            "informational_only": [],
        }
        for reason in reasons:
            if reason in {"private_api_health_degraded", "auth_validation_unproven"}:
                classifications["execution_blocker"].append(reason)
            elif reason in {"lifecycle_snapshot_absent", "user_stream_not_connected"}:
                classifications["promotion_blocker"].append(reason)
            elif reason in {"capability_evidence_stale", "sequence_evidence_degraded", "checksum_evidence_degraded", "public_market_data_not_connected"}:
                classifications["confidence_haircut"].append(reason)
            else:
                classifications["informational_only"].append(reason)
        return classifications

    def resolve(
        self,
        provider_id: str,
        *,
        connector: Any | None = None,
        live: Any | None = None,
        now: datetime | None = None,
    ) -> ProviderCapabilityMatrix:
        base = provider_capability_matrix(provider_id)
        evidence = self._inspect(provider_id=provider_id, connector=connector, live=live, now=now)
        self._evidence[provider_id] = evidence
        user_stream_confidence = base.user_stream_confidence
        lifecycle_completeness = base.lifecycle_completeness
        if evidence.partial and provider_id != "kraken_derivatives":
            user_stream_confidence = "rest_history_only"
        if evidence.lifecycle_snapshot_count <= 0:
            lifecycle_completeness = "partial_without_snapshot"
        if provider_id == "kraken_spot" and bool(evidence.metadata.get("ws_lifecycle_observability", False)):
            user_stream_confidence = "user_stream_plus_rest_repair"
            lifecycle_completeness = "strong_without_replace"
        if provider_id == "kraken_spot" and bool(evidence.metadata.get("single_process_lifecycle_equivalent", False)):
            user_stream_confidence = "single_process_rest_repair"
            lifecycle_completeness = "strong_without_replace"
        replace_supported = bool(getattr(live, "supports_replace", getattr(connector, "supports_replace", base.replace_supported)))
        expire_supported = bool(getattr(live, "supports_expire", getattr(connector, "supports_expire", base.expire_supported)))
        return ProviderCapabilityMatrix(
            provider_id=base.provider_id,
            unrealized_pnl_truth_support=base.unrealized_pnl_truth_support,
            realized_pnl_truth_support=base.realized_pnl_truth_support,
            lifecycle_completeness=lifecycle_completeness,
            replace_supported=replace_supported,
            expire_supported=expire_supported,
            fee_truth_confidence=base.fee_truth_confidence,
            user_stream_confidence=user_stream_confidence,
            metadata={
                **dict(base.metadata),
                "capability_evidence": {
                    "freshness_seconds": evidence.evidence_freshness_seconds,
                    "reasons": list(evidence.reasons),
                    "classifications": dict(evidence.metadata.get("classifications", {}) or {}),
                    "partial": evidence.partial,
                    "sequence_ok": evidence.sequence_ok,
                    "checksum_ok": evidence.checksum_ok,
                    "lifecycle_snapshot_count": evidence.lifecycle_snapshot_count,
                    "lifecycle_snapshot_seeded": bool(evidence.metadata.get("lifecycle_snapshot_seeded", False)),
                    "ws_lifecycle_observability": bool(evidence.metadata.get("ws_lifecycle_observability", False)),
                    "single_process_lifecycle_equivalent": bool(evidence.metadata.get("single_process_lifecycle_equivalent", False)),
                },
            },
        )

    def for_provider(self, provider_id: str) -> ProviderCapabilityMatrix:
        return self.resolve(provider_id)

    def last_evidence(self, provider_id: str) -> CapabilityEvidence | None:
        return self._evidence.get(provider_id)
