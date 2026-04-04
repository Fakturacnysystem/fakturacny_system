from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import AllocatorDecisionReport


class PortfolioAllocatorService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def allocate(
        self,
        *,
        capital_envelope: dict[str, Any],
        expectancy: dict[str, Any],
        selected_candidate: dict[str, Any] | None,
    ) -> dict[str, Any]:
        ts = datetime.now(timezone.utc)
        pair_budget = float(capital_envelope.get("pair_level_cap", 0.0) or 0.0)
        playbook_budget = float(capital_envelope.get("playbook_level_cap", 0.0) or 0.0)
        regime_budget = float(capital_envelope.get("regime_level_cap", 0.0) or 0.0)
        expectancy_bps = float(expectancy.get("net_expectancy_bps", 0.0) or 0.0)
        false_positive_rate = float(expectancy.get("false_positive_rate", 0.0) or 0.0)
        dead_capital_pressure = float(capital_envelope.get("dead_capital_pressure", 0.0) or 0.0)
        recovery_mode = expectancy_bps < float(self.settings.expectancy.size_down_expectancy_floor_bps) or false_positive_rate > float(self.settings.operator_kpis.false_positive_warn)
        aggressiveness_scalar = max(
            0.10,
            min(
                1.0,
                0.60
                + expectancy_bps / 40.0
                - false_positive_rate * 0.50
                - dead_capital_pressure * 0.25
                - (0.25 if recovery_mode else 0.0),
            ),
        )
        selected_notional = 0.0 if selected_candidate is None else float(selected_candidate.get("target_notional", 0.0) or 0.0)
        recommended_notional = min(pair_budget, playbook_budget, regime_budget, selected_notional * aggressiveness_scalar if selected_notional > 0.0 else pair_budget * aggressiveness_scalar)
        confidence = 0.0 if selected_candidate is None else float(selected_candidate.get("confidence", 0.0) or 0.0)
        confidence_bucket = "high" if confidence >= 0.75 else "medium" if confidence >= 0.50 else "low"
        quality = 0.0 if selected_candidate is None else float(selected_candidate.get("quality_of_edge", 0.0) or 0.0)
        execution_quality_bucket = "high" if quality >= 0.75 else "medium" if quality >= 0.50 else "low"
        report = AllocatorDecisionReport(
            ts=ts,
            recommended_notional=recommended_notional,
            pair_budget=pair_budget,
            playbook_budget=playbook_budget,
            regime_budget=regime_budget,
            recovery_mode=recovery_mode,
            aggressiveness_scalar=aggressiveness_scalar,
            confidence_bucket=confidence_bucket,
            execution_quality_bucket=execution_quality_bucket,
            reasons=[
                "recovery_mode" if recovery_mode else "",
                "selected_candidate_missing" if selected_candidate is None else "",
                "dead_capital_pressure_high" if dead_capital_pressure >= 0.5 else "",
            ],
            metadata={
                "expectancy_bps": expectancy_bps,
                "dead_capital_pressure": dead_capital_pressure,
                "false_positive_rate": false_positive_rate,
            },
        )
        payload = asdict(report)
        payload["reasons"] = [reason for reason in payload["reasons"] if reason]
        return {
            "allocator_decisions": payload,
            "capital_allocation_matrix": {
                "ts": payload["ts"],
                "pair_budget": pair_budget,
                "playbook_budget": playbook_budget,
                "regime_budget": regime_budget,
                "recommended_notional": recommended_notional,
            },
            "confidence_bucket_exposure": {
                "ts": payload["ts"],
                "confidence_bucket": confidence_bucket,
                "execution_quality_bucket": execution_quality_bucket,
                "recommended_notional": recommended_notional,
            },
            "playbook_pair_budget_matrix": {
                "ts": payload["ts"],
                "selected_playbook": None if selected_candidate is None else selected_candidate.get("playbook"),
                "selected_symbol": None if selected_candidate is None else selected_candidate.get("symbol"),
                "playbook_budget": playbook_budget,
                "pair_budget": pair_budget,
            },
            "recovery_mode_report": {
                "ts": payload["ts"],
                "recovery_mode": recovery_mode,
                "trigger_expectancy_bps": expectancy_bps,
            },
            "aggressiveness_scaler_report": {
                "ts": payload["ts"],
                "aggressiveness_scalar": aggressiveness_scalar,
                "dead_capital_pressure": dead_capital_pressure,
                "false_positive_rate": false_positive_rate,
            },
        }

