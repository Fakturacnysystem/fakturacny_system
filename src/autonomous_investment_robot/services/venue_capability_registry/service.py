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
        if lifecycle_snapshot_count <= 0 and live is not None and hasattr(live, "lifecycle_snapshot"):
            try:
                lifecycle_snapshot_count = len(live.lifecycle_snapshot())
            except Exception:
                lifecycle_snapshot_count = 0
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
        reasons: list[str] = []
        partial = False
        if not user_stream_connected and provider_id != "kraken_derivatives":
            reasons.append("user_stream_not_connected")
            partial = True
        if lifecycle_snapshot_count <= 0:
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
            },
        )

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
                    "partial": evidence.partial,
                    "sequence_ok": evidence.sequence_ok,
                    "checksum_ok": evidence.checksum_ok,
                    "lifecycle_snapshot_count": evidence.lifecycle_snapshot_count,
                },
            },
        )

    def for_provider(self, provider_id: str) -> ProviderCapabilityMatrix:
        return self.resolve(provider_id)

    def last_evidence(self, provider_id: str) -> CapabilityEvidence | None:
        return self._evidence.get(provider_id)
