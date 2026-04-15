from __future__ import annotations

from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import MarketIntegrityStatus, ProviderCapabilityMatrix, VenueLimitDecision


class SharedVenueLimitGovernor:
    def _classify_reasons(self, reasons: list[str]) -> dict[str, list[str]]:
        classifications = {
            "execution_blocker": [],
            "promotion_blocker": [],
            "confidence_haircut": [],
            "informational_only": [],
        }
        for reason in reasons:
            if reason in {"capability_mismatch_under_stress"}:
                classifications["execution_blocker"].append(reason)
            elif reason in {"user_stream_confidence_partial", "lifecycle_completeness_not_strong"}:
                classifications["promotion_blocker"].append(reason)
            elif reason in {"expire_semantics_partial"}:
                classifications["confidence_haircut"].append(reason)
            else:
                classifications["informational_only"].append(reason)
        return classifications

    def evaluate(
        self,
        *,
        symbol: str,
        provider_id: str,
        market_integrity: MarketIntegrityStatus,
        capability: ProviderCapabilityMatrix,
    ) -> VenueLimitDecision:
        reasons = list(market_integrity.reasons)
        classification_reasons: list[str] = []
        action = "continue"
        size_multiplier = 1.0
        reduce_only_only = False

        if market_integrity.action == "halt":
            action = "halt"
            size_multiplier = 0.0
        elif market_integrity.action == "flatten_only":
            action = "flatten_only"
            size_multiplier = 0.0
            reduce_only_only = True
        elif market_integrity.action == "degrade":
            action = "degrade"
            size_multiplier = min(size_multiplier, 0.25)

        if capability.user_stream_confidence == "rest_history_only":
            size_multiplier = min(size_multiplier, 0.50)
            reasons.append("user_stream_confidence_partial")
            classification_reasons.append("user_stream_confidence_partial")
        if capability.lifecycle_completeness != "strong_without_replace":
            size_multiplier = min(size_multiplier, 0.50)
            reasons.append("lifecycle_completeness_not_strong")
            classification_reasons.append("lifecycle_completeness_not_strong")
        if not capability.replace_supported:
            reasons.append("replace_fail_closed")
        if not capability.expire_supported:
            size_multiplier = min(size_multiplier, 0.50)
            reasons.append("expire_semantics_partial")
            classification_reasons.append("expire_semantics_partial")

        if capability.user_stream_confidence == "rest_history_only" and market_integrity.score < 0.60:
            reasons.append("capability_mismatch_under_stress")
            classification_reasons.append("capability_mismatch_under_stress")
            if action in {"continue", "degrade"}:
                action = "flatten_only"
                size_multiplier = 0.0
                reduce_only_only = True
        classifications = self._classify_reasons(classification_reasons)

        return VenueLimitDecision(
            symbol=symbol,
            provider_id=provider_id,
            ts=datetime.now(timezone.utc),
            action=action,
            size_multiplier=max(0.0, min(1.0, size_multiplier)),
            reduce_only_only=reduce_only_only,
            reasons=sorted(set(reasons)),
            metadata={
                "market_integrity_action": market_integrity.action,
                "market_integrity_score": market_integrity.score,
                "lifecycle_completeness": capability.lifecycle_completeness,
                "user_stream_confidence": capability.user_stream_confidence,
                "classifications": classifications,
                "promotion_blocked": bool(classifications["promotion_blocker"]),
                "execution_caution_only": action == "continue" and size_multiplier < 1.0,
            },
        )
