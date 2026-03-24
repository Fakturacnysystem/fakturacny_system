from __future__ import annotations

from datetime import datetime, timezone

from autonomous_investment_robot.core.contracts import MarketHealthSnapshot, MarketIntegrityStatus, MetaGovernorDecision, SystemHealthSnapshot, TruthConfidenceLevel, TruthConfidenceSnapshot, VenueLimitDecision


class HealthService:
    def _rollout_cap(self, rollout_stage: str) -> float:
        return {
            "paper": 0.0,
            "shadow": 0.0,
            "tiny_live": 0.05,
            "canary_live": 0.10,
            "limited_live": 0.25,
            "normal_live": 1.0,
        }.get(rollout_stage, 0.25)

    def evaluate(
        self,
        *,
        market_health: MarketHealthSnapshot,
        risk_mode: str,
        reconciliation_ok: bool,
        api_error_burst: int = 0,
        order_reject_burst: int = 0,
        abnormal_latency_ms: float = 0.0,
        slippage_drift_bps: float = 0.0,
        unexplained_pnl_deviation_pct: float = 0.0,
        anomaly_pressure: float = 0.0,
        market_integrity_status: MarketIntegrityStatus | None = None,
    ) -> SystemHealthSnapshot:
        score = 1.0
        reasons = list(market_health.reasons)
        if not reconciliation_ok:
            score -= 0.4
            reasons.append("reconciliation_bad")
        if api_error_burst >= 3:
            score -= 0.2
            reasons.append("api_error_burst")
        if order_reject_burst >= 3:
            score -= 0.15
            reasons.append("reject_burst")
        if abnormal_latency_ms > 1000:
            score -= 0.15
            reasons.append("abnormal_latency")
        if slippage_drift_bps > 10:
            score -= 0.15
            reasons.append("slippage_drift")
        if unexplained_pnl_deviation_pct > 0.5:
            score -= 0.2
            reasons.append("unexplained_pnl_deviation")
        if anomaly_pressure > 0.5:
            score -= 0.1
            reasons.append("anomaly_pressure")
        if market_integrity_status is not None:
            reasons.extend(market_integrity_status.reasons)
            if market_integrity_status.action == "degrade":
                score = min(score, max(0.60, float(market_integrity_status.score)))
                reasons.append("market_integrity_degrade")
            elif market_integrity_status.action == "flatten_only":
                score = min(score, max(0.55, float(market_integrity_status.score)))
                reasons.append("market_integrity_flatten_only")
            elif market_integrity_status.action == "halt":
                score = min(score, min(0.15, float(market_integrity_status.score)))
                reasons.append("market_integrity_halt")

        action = "continue"
        if score <= 0.2:
            action = "halt_and_flatten"
        elif score <= 0.45:
            action = "halt"
        elif score <= 0.7:
            action = "degrade"

        return SystemHealthSnapshot(
            ts=datetime.now(timezone.utc),
            risk_mode=risk_mode,
            health_score=max(0.0, score),
            exchange_health_score=market_health.exchange_health_score,
            market_quality_score=market_health.market_quality_score,
            execution_health_score=max(0.0, 1.0 - min(1.0, abnormal_latency_ms / 2000.0)),
            drift_pressure=min(1.0, max(slippage_drift_bps / 20.0, unexplained_pnl_deviation_pct / 2.0)),
            anomaly_pressure=min(1.0, anomaly_pressure),
            overtrading_pressure=min(1.0, order_reject_burst / 5.0),
            action=action,
            reasons=reasons,
            metadata={
                "api_error_burst": api_error_burst,
                "order_reject_burst": order_reject_burst,
                "market_integrity_action": None if market_integrity_status is None else market_integrity_status.action,
            },
        )

    def govern(
        self,
        *,
        symbol: str,
        health_snapshot: SystemHealthSnapshot,
        rollout_stage: str,
        truth_confidence: TruthConfidenceSnapshot | None = None,
        reconciliation_action: str = "continue",
        reconciliation_code: str = "ok",
        market_integrity_status: MarketIntegrityStatus | None = None,
        venue_limit_decision: VenueLimitDecision | None = None,
    ) -> MetaGovernorDecision:
        size_multiplier = self._rollout_cap(rollout_stage)
        action = "continue"
        forced_risk_mode: str | None = None
        reasons = list(health_snapshot.reasons)
        metadata = {
            "rollout_stage": rollout_stage,
            "reconciliation_action": reconciliation_action,
            "reconciliation_code": reconciliation_code,
            "base_rollout_cap": size_multiplier,
        }

        truth_action = "continue"
        market_integrity_action = "continue" if market_integrity_status is None else market_integrity_status.action
        venue_limit_action = "continue" if venue_limit_decision is None else venue_limit_decision.action
        if truth_confidence is not None:
            metadata["truth_confidence"] = {
                "fill": truth_confidence.fill_truth_confidence.level.value,
                "fee": truth_confidence.fee_truth_confidence.level.value,
                "realized_pnl": truth_confidence.realized_pnl_confidence.level.value,
                "balance": truth_confidence.balance_truth_confidence.level.value,
                "exposure": truth_confidence.exposure_truth_confidence.level.value,
                "market_data": truth_confidence.market_data_truth_confidence.level.value,
                "unrealized_pnl": None if truth_confidence.unrealized_pnl_confidence is None else truth_confidence.unrealized_pnl_confidence.level.value,
            }
            reasons.extend(truth_confidence.reasons)
            truth_levels = {
                truth_confidence.fill_truth_confidence.level.value,
                truth_confidence.fee_truth_confidence.level.value,
                truth_confidence.realized_pnl_confidence.level.value,
                truth_confidence.balance_truth_confidence.level.value,
                truth_confidence.exposure_truth_confidence.level.value,
                truth_confidence.market_data_truth_confidence.level.value,
            }
            soft_truth_levels = set()
            if truth_confidence.unrealized_pnl_confidence is not None:
                soft_truth_levels.add(truth_confidence.unrealized_pnl_confidence.level.value)
            if TruthConfidenceLevel.UNAVAILABLE.value in truth_levels:
                truth_action = "flatten_only"
            elif TruthConfidenceLevel.UNAVAILABLE.value in soft_truth_levels:
                truth_action = "degrade"
            elif TruthConfidenceLevel.PROXY.value in truth_levels:
                truth_action = "degrade"
            elif TruthConfidenceLevel.PROXY.value in soft_truth_levels:
                truth_action = "degrade"
            else:
                truth_action = truth_confidence.overall_action

        if market_integrity_status is not None:
            metadata["market_integrity"] = {
                "score": market_integrity_status.score,
                "action": market_integrity_status.action,
                "confidence": market_integrity_status.confidence,
            }
            reasons.extend(market_integrity_status.reasons)
        if venue_limit_decision is not None:
            metadata["venue_limit"] = {
                "action": venue_limit_decision.action,
                "size_multiplier": venue_limit_decision.size_multiplier,
                "reduce_only_only": venue_limit_decision.reduce_only_only,
            }
            reasons.extend(venue_limit_decision.reasons)

        if health_snapshot.action == "halt_and_flatten" or reconciliation_action == "halt_and_flatten":
            action = "force_halt_and_flatten"
            forced_risk_mode = "kill-switch"
        elif health_snapshot.action == "halt" or reconciliation_action == "halt" or market_integrity_action == "halt" or venue_limit_action == "halt":
            action = "force_halt"
            forced_risk_mode = "kill-switch"
        elif reconciliation_action == "flatten_only" or truth_action == "flatten_only" or market_integrity_action == "flatten_only" or venue_limit_action == "flatten_only":
            action = "force_flatten_only"
            forced_risk_mode = "flatten-only"
            size_multiplier = 0.0
        elif (
            health_snapshot.action == "degrade"
            or reconciliation_action == "degrade"
            or truth_action == "degrade"
            or market_integrity_action == "degrade"
            or venue_limit_action == "degrade"
        ):
            action = "force_degraded"
            forced_risk_mode = "degraded"
            size_multiplier = min(size_multiplier, 0.25)
        elif health_snapshot.health_score < 0.75 or health_snapshot.overtrading_pressure > 0.4:
            action = "reduce_max_size"
            forced_risk_mode = "cautious"
            size_multiplier = min(size_multiplier, 0.5)

        if venue_limit_decision is not None:
            size_multiplier = min(size_multiplier, max(0.0, float(venue_limit_decision.size_multiplier)))

        if health_snapshot.exchange_health_score < 0.2 or health_snapshot.market_quality_score < 0.2:
            action = "disable_symbol"
            forced_risk_mode = forced_risk_mode or "defensive"
            size_multiplier = 0.0
            reasons.append("exchange_or_market_quality_bad")

        if health_snapshot.execution_health_score < 0.35 and action == "continue":
            action = "reduce_max_size"
            forced_risk_mode = forced_risk_mode or "cautious"
            size_multiplier = min(size_multiplier, 0.5)
            reasons.append("execution_health_bad")

        if action == "continue":
            if rollout_stage == "shadow":
                action = "disable_symbol"
                reasons.append("rollout_no_live_ordering")
            elif rollout_stage == "paper":
                reasons.append("paper_rollout_cap")

        return MetaGovernorDecision(
            symbol=symbol,
            ts=datetime.now(timezone.utc),
            action=action,
            size_multiplier=max(0.0, min(1.0, size_multiplier)),
            forced_risk_mode=forced_risk_mode,
            disabled_symbols=[symbol] if action == "disable_symbol" else [],
            reasons=reasons,
            metadata=metadata,
        )
