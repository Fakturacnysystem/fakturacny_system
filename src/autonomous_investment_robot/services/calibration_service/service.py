from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autonomous_investment_robot.core.contracts import CalibrationProfile


class CalibrationService:
    def __init__(self, run_dir: str | None = None) -> None:
        self.run_dir = None if run_dir is None else Path(run_dir)
        self._profile = CalibrationProfile(
            ts=datetime.now(timezone.utc),
            recent_loss_rate=0.0,
            recent_execution_miss_rate=0.0,
            recent_truth_gap_rate=0.0,
            no_trade_bias=0.0,
            fragility_bias=0.0,
            size_bias=1.0,
            reasons=["default_calibration"],
            heuristic=True,
        )

    def update_from_episodes(self, episodes: list[Any]) -> CalibrationProfile:
        recent = list(episodes[-50:])
        if not recent:
            return self._profile
        loss_rate = sum(1 for ep in recent if float(getattr(ep, "realized_pnl", 0.0) or 0.0) < 0.0) / len(recent)
        execution_miss_rate = sum(1 for ep in recent if "execution" in str(getattr(ep, "failure_mode", ""))) / len(recent)
        truth_gap_rate = sum(1 for ep in recent if "truth" in str(getattr(ep, "failure_mode", ""))) / len(recent)
        negative_pnls = [abs(float(getattr(ep, "realized_pnl", 0.0) or 0.0)) for ep in recent if float(getattr(ep, "realized_pnl", 0.0) or 0.0) < 0.0]
        avg_loss_severity = sum(negative_pnls) / max(len(negative_pnls), 1) if negative_pnls else 0.0
        loss_severity_norm = min(1.0, avg_loss_severity / 50.0)
        event_failure_rate = sum(1 for ep in recent if "event" in str(getattr(ep, "failure_mode", ""))) / len(recent)
        shadow_veto_bias = min(0.45, 0.15 * execution_miss_rate + 0.15 * truth_gap_rate + 0.10 * loss_rate + 0.10 * loss_severity_norm)
        spre_wait_bias = min(0.35, 0.10 * execution_miss_rate + 0.10 * truth_gap_rate + 0.10 * event_failure_rate + 0.05 * loss_severity_norm)
        dominance_caution_bias = min(0.40, 0.15 * loss_rate + 0.10 * loss_severity_norm + 0.10 * truth_gap_rate)
        self._profile = CalibrationProfile(
            ts=datetime.now(timezone.utc),
            recent_loss_rate=loss_rate,
            recent_execution_miss_rate=execution_miss_rate,
            recent_truth_gap_rate=truth_gap_rate,
            no_trade_bias=min(0.4, 0.2 * loss_rate + 0.2 * truth_gap_rate),
            fragility_bias=min(0.4, 0.25 * execution_miss_rate + 0.15 * truth_gap_rate),
            size_bias=max(0.35, 1.0 - 0.35 * loss_rate - 0.2 * execution_miss_rate),
            reasons=["episode_memory_calibration"],
            heuristic=True,
            metadata={
                "sample_size": len(recent),
                "avg_loss_severity": avg_loss_severity,
                "loss_severity_norm": loss_severity_norm,
                "event_failure_rate": event_failure_rate,
                "shadow_veto_bias": shadow_veto_bias,
                "spre_wait_bias": spre_wait_bias,
                "dominance_caution_bias": dominance_caution_bias,
            },
        )
        if self.run_dir is not None:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            out = self.run_dir / "calibration_profile.json"
            out.write_text(json.dumps(self._profile.__dict__, sort_keys=True, default=str, indent=2), encoding="utf-8")
        return self._profile

    def current_profile(self) -> CalibrationProfile:
        return self._profile
