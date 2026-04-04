from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import ExperimentRegistryReport


class ExperimentsService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def evaluate(
        self,
        *,
        playbook_candidates: list[dict[str, Any]],
        expectancy: dict[str, Any],
        health_summary: dict[str, Any],
    ) -> dict[str, Any]:
        ts = datetime.now(timezone.utc)
        promotion_score = float(expectancy.get("promotion_score", 0.0) or 0.0)
        rollback_triggered = promotion_score < max(0.0, float(self.settings.experiments.promotion_score_min) - 0.15) or bool(health_summary.get("blocking_reasons"))
        active_variants = sorted({str(candidate.get("playbook", "")) for candidate in playbook_candidates if candidate.get("live_enabled")})
        shadow_variants = sorted({str(candidate.get("playbook", "")) for candidate in playbook_candidates if not candidate.get("live_enabled")})
        report = ExperimentRegistryReport(
            ts=ts,
            enabled=bool(self.settings.experiments.enabled),
            promotion_score=promotion_score,
            rollback_triggered=rollback_triggered,
            active_variants=active_variants,
            shadow_variants=shadow_variants,
            reasons=[
                "rollback_triggered" if rollback_triggered else "",
                "sample_guard_unmet" if not bool(expectancy.get("metadata", {}).get("sample_guard", False)) else "",
            ],
            metadata={
                "blocking_reasons": list(health_summary.get("blocking_reasons", []) or []),
                "evidence_min_trades": int(self.settings.experiments.evidence_min_trades),
            },
        )
        payload = asdict(report)
        payload["reasons"] = [reason for reason in payload["reasons"] if reason]
        return {
            "experiment_registry": payload,
            "experiment_results_summary": {
                "ts": payload["ts"],
                "active_variants": active_variants,
                "shadow_variants": shadow_variants,
            },
            "promotion_gate_report": {
                "ts": payload["ts"],
                "promotion_score": promotion_score,
                "promotion_score_min": float(self.settings.experiments.promotion_score_min),
                "eligible": promotion_score >= float(self.settings.experiments.promotion_score_min),
            },
            "rollback_trigger_report": {
                "ts": payload["ts"],
                "rollback_triggered": rollback_triggered,
                "reasons": payload["reasons"],
            },
            "regime_segmented_experiment_report": {
                "ts": payload["ts"],
                "segments": {},
            },
        }

