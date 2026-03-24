from __future__ import annotations

from autonomous_investment_robot.core.contracts import (
    CapabilityEvidence,
    MarketHealthSnapshot,
    MarketIntegrityEvidence,
    MarketIntegrityStatus,
    MarketSnapshot,
    ProviderCapabilityMatrix,
)


class MarketIntegrityService:
    def assess(
        self,
        *,
        symbol: str,
        provider_id: str,
        snapshot: MarketSnapshot,
        market_health: MarketHealthSnapshot,
        capability: ProviderCapabilityMatrix,
        integrity_evidence: MarketIntegrityEvidence | None = None,
        capability_evidence: CapabilityEvidence | None = None,
    ) -> MarketIntegrityStatus:
        reasons = list(market_health.reasons)
        score = min(
            float(market_health.symbol_health_score),
            float(market_health.exchange_health_score),
            float(market_health.market_quality_score),
        )
        metadata = {
            "spread_bps": snapshot.spread_bps,
            "depth_notional": snapshot.depth_notional,
            "market_health": {
                "symbol_health_score": market_health.symbol_health_score,
                "exchange_health_score": market_health.exchange_health_score,
                "market_quality_score": market_health.market_quality_score,
            },
            "capability": {
                "lifecycle_completeness": capability.lifecycle_completeness,
                "fee_truth_confidence": capability.fee_truth_confidence,
                "user_stream_confidence": capability.user_stream_confidence,
                "replace_supported": capability.replace_supported,
                "expire_supported": capability.expire_supported,
            },
        }
        if integrity_evidence is not None:
            metadata["integrity_evidence"] = {
                "feed_age_seconds": integrity_evidence.feed_age_seconds,
                "sequence_ok": integrity_evidence.sequence_ok,
                "checksum_ok": integrity_evidence.checksum_ok,
                "gap_count": integrity_evidence.gap_count,
                "checksum_mismatch_count": integrity_evidence.checksum_mismatch_count,
                "evidence_confidence": integrity_evidence.evidence_confidence,
            }
            if integrity_evidence.feed_age_seconds > 30.0:
                score -= 0.15
                reasons.append("integrity_evidence_stale")
            if integrity_evidence.gap_count > 0:
                score -= min(0.25, 0.05 * integrity_evidence.gap_count)
                reasons.append("dynamic_sequence_gap")
            if integrity_evidence.checksum_mismatch_count > 0:
                score -= min(0.25, 0.08 * integrity_evidence.checksum_mismatch_count)
                reasons.append("dynamic_checksum_mismatch")
            if not bool(integrity_evidence.metadata.get("public_market_data_connected", True)):
                score -= 0.15
                reasons.append("public_market_data_unproven")
            if int(integrity_evidence.metadata.get("book_repeat_count", 0) or 0) >= 5:
                score -= 0.10
                reasons.append("book_repeating_without_change")
            if float(integrity_evidence.metadata.get("seconds_since_distinct_book_change", 0.0) or 0.0) > 60.0:
                score -= 0.10
                reasons.append("book_change_stale")
        if capability_evidence is not None:
            metadata["capability_evidence"] = {
                "freshness_seconds": capability_evidence.evidence_freshness_seconds,
                "user_stream_connected": capability_evidence.user_stream_connected,
                "lifecycle_snapshot_count": capability_evidence.lifecycle_snapshot_count,
                "partial": capability_evidence.partial,
            }
            if capability_evidence.partial:
                score -= 0.10
                reasons.append("capability_evidence_partial")
            if not bool(capability_evidence.metadata.get("private_api_healthy", True)):
                score -= 0.20
                reasons.append("private_api_health_degraded")
            if bool(capability_evidence.metadata.get("has_credentials", False)) and not bool(capability_evidence.metadata.get("auth_validated", True)):
                score -= 0.05
                reasons.append("auth_validation_unproven")
            if not bool(capability_evidence.metadata.get("public_market_data_connected", True)):
                score -= 0.10
                reasons.append("public_market_data_unproven")

        if capability.user_stream_confidence == "rest_history_only":
            score -= 0.05
            reasons.append("user_stream_repair_partial")
        if capability.lifecycle_completeness != "strong_without_replace":
            score -= 0.10
            reasons.append("lifecycle_capability_partial")
        if market_health.feed_stale:
            reasons.append("market_integrity_stale_feed")
        if not market_health.sequence_ok:
            reasons.append("market_integrity_sequence_gap")
        if not market_health.checksum_ok:
            reasons.append("market_integrity_checksum_gap")
        if snapshot.depth_notional <= 0.0:
            score -= 0.35
            reasons.append("market_integrity_book_unavailable")

        action = "continue"
        if market_health.feed_stale or not market_health.sequence_ok or not market_health.checksum_ok:
            action = "flatten_only" if capability.user_stream_confidence == "rest_history_only" else "degrade"
        if integrity_evidence is not None and (not integrity_evidence.sequence_ok or not integrity_evidence.checksum_ok):
            action = "flatten_only" if capability.user_stream_confidence == "rest_history_only" else "degrade"
        elif market_health.market_quality_score < 0.50:
            action = "degrade"

        if capability.user_stream_confidence == "rest_history_only" and market_health.exchange_health_score < 0.60:
            action = "flatten_only"
            reasons.append("capability_mismatch_under_exchange_stress")
        if integrity_evidence is not None and integrity_evidence.evidence_confidence == "weak":
            action = "flatten_only"
            reasons.append("integrity_confidence_weak")
        if capability_evidence is not None and not bool(capability_evidence.metadata.get("private_api_healthy", True)):
            action = "flatten_only"

        score = max(0.0, min(1.0, score))
        if score <= 0.20:
            action = "halt"

        confidence = "strong" if capability.user_stream_confidence != "rest_history_only" else "partial"
        if integrity_evidence is not None and integrity_evidence.evidence_confidence in {"weak", "partial"}:
            confidence = integrity_evidence.evidence_confidence
        return MarketIntegrityStatus(
            symbol=symbol,
            provider_id=provider_id,
            ts=snapshot.ts,
            score=score,
            action=action,
            confidence=confidence,
            reasons=sorted(set(reasons)),
            metadata=metadata,
        )
