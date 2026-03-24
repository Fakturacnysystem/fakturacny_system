from __future__ import annotations

from autonomous_investment_robot.core.contracts import ShadowRivalReport, SPREDecision


class ShadowRivalService:
    def __init__(self, calibration_service: object | None = None) -> None:
        self.calibration_service = calibration_service

    def evaluate(
        self,
        *,
        symbol: str,
        ts: object,
        spre_decision: SPREDecision,
        quantum_state: object | None = None,
        edge_immunity_decision: object | None = None,
        event_intelligence_report: object | None = None,
        synthetic_affect_state: object | None = None,
        execution_simulation_report: object | None = None,
    ) -> ShadowRivalReport:
        calibration = self.calibration_service.current_profile() if self.calibration_service is not None else None
        calibration_meta = {} if calibration is None else dict(getattr(calibration, "metadata", {}) or {})
        collapse = getattr(quantum_state, "collapse_decision", object()) if quantum_state is not None else object()
        edge_report = getattr(edge_immunity_decision, "report", object()) if edge_immunity_decision is not None else object()

        no_trade_probability = float(getattr(collapse, "no_trade_probability", 0.0) or 0.0)
        fragility = max(
            float(getattr(collapse, "execution_fragility_score", 0.0) or 0.0),
            float(getattr(edge_report, "fragility_index", 0.0) or 0.0),
        )
        event_risk = 0.0 if event_intelligence_report is None else float(getattr(event_intelligence_report, "overall_risk_score", 0.0) or 0.0)
        synthetic_stress = 0.0 if synthetic_affect_state is None else max(
            float(getattr(synthetic_affect_state, "stress", 0.0) or 0.0),
            float(getattr(synthetic_affect_state, "fear", 0.0) or 0.0),
        )
        simulation_break = 0.0 if execution_simulation_report is None else (
            1.0 if str(getattr(execution_simulation_report, "recommended_action", "continue")) == "no_trade" else 0.5 if str(getattr(execution_simulation_report, "recommended_action", "continue")) == "wait" else 0.0
        )

        spre_meta = dict(getattr(spre_decision, "metadata", {}) or {})
        dominant_failure_modes = list(spre_meta.get("dominant_failure_modes", []) or [])
        action_scores = {str(k): float(v) for k, v in dict(spre_meta.get("dominance_scores", {}) or {}).items()}
        action_gap = float(spre_meta.get("action_gap_bps", 0.0) or 0.0)
        chosen_survival_ratio = float(spre_meta.get("chosen_survival_ratio", 0.0) or 0.0)
        ambiguity_penalty = float(spre_meta.get("ambiguity_penalty", 0.0) or 0.0)
        internal_action = str(spre_meta.get("internal_action", spre_decision.dominant_action))
        branch_disagreement = float(spre_meta.get("branch_disagreement", 0.0) or 0.0)
        scenario_drift = float(spre_meta.get("scenario_drift", 0.0) or 0.0)
        wait_score = float(action_scores.get("wait", 0.0))
        no_trade_score = float(action_scores.get("no_trade", 0.0))
        trade_now_score = float(action_scores.get("trade_now", 0.0))
        trade_smaller_score = float(action_scores.get("trade_smaller", 0.0))

        failure_cluster_score = min(
            1.0,
            0.22 * sum(mode in {"integrity_break", "liquidity_vacuum", "execution_break", "adverse_follow_through", "crowding_unwind"} for mode in dominant_failure_modes),
        )
        thesis_break_score = min(
            1.0,
            no_trade_probability * 0.25
            + fragility * 0.18
            + event_risk * 0.16
            + synthetic_stress * 0.10
            + simulation_break * 0.16
            + failure_cluster_score * 0.15
            + float(calibration_meta.get("shadow_veto_bias", 0.0) or 0.0),
        )
        ambiguity_score = min(
            1.0,
            ambiguity_penalty * 0.45
            + branch_disagreement * 0.18
            + scenario_drift * 0.14
            + (0.12 if action_gap < 1.25 else 0.0)
            + (0.08 if internal_action == "probe" else 0.0),
        )
        kill_path_score = min(
            1.0,
            failure_cluster_score * 0.40
            + simulation_break * 0.28
            + max(0.0, 0.55 - chosen_survival_ratio) * 0.45
            + (0.15 if no_trade_score >= max(trade_now_score, trade_smaller_score) else 0.0),
        )
        wait_dominance_score = min(
            1.0,
            ambiguity_score * 0.40
            + max(0.0, wait_score - max(trade_now_score, trade_smaller_score, 0.0)) / 10.0
            + (0.12 if action_gap < 1.0 else 0.0),
        )
        critique_score = min(
            1.0,
            thesis_break_score * 0.45 + kill_path_score * 0.35 + wait_dominance_score * 0.20,
        )

        action = "continue"
        allowed = True
        reasons: list[str] = []

        if spre_decision.dominant_action == "no_trade":
            action = "no_trade"
            allowed = False
            reasons.append("spre_no_trade_dominant")
        elif kill_path_score >= 0.68 or thesis_break_score >= 0.80:
            action = "no_trade"
            allowed = False
            reasons.append("shadow_rival_veto")
        elif spre_decision.dominant_action == "wait" or wait_dominance_score >= 0.62:
            action = "wait"
            allowed = False
            reasons.append("shadow_wait_dominance")
        elif spre_decision.dominant_action == "trade_smaller" or critique_score >= 0.48 or ambiguity_score >= 0.55:
            action = "trade_smaller"
            reasons.append("shadow_rival_size_cut")
        else:
            reasons.append("shadow_rival_allows_trade")

        if event_risk >= 0.6:
            reasons.append("adversarial_event_cluster")
        if simulation_break >= 1.0:
            reasons.append("shadow_execution_break")
        if chosen_survival_ratio < 0.45:
            reasons.append("shadow_survival_low")
        if action_gap < 1.0:
            reasons.append("shadow_ambiguity_gap")
        if failure_cluster_score >= 0.4:
            reasons.append("shadow_failure_cluster")

        narrative = (
            f"shadow_action={action}; critique_score={critique_score:.2f}; thesis_break={thesis_break_score:.2f}; "
            f"kill_path={kill_path_score:.2f}; wait_score={wait_dominance_score:.2f}; "
            f"spre_action={spre_decision.dominant_action}; survival_ratio={chosen_survival_ratio:.2f}"
        )
        return ShadowRivalReport(
            symbol=symbol,
            ts=ts,  # type: ignore[arg-type]
            action=action,
            allowed=allowed,
            critique_score=critique_score,
            reasons=sorted(set(reasons)),
            narrative=narrative,
            heuristic=True,
            metadata={
                "spre_narrative": spre_decision.narrative,
                "event_risk": event_risk,
                "synthetic_stress": synthetic_stress,
                "simulation_break": simulation_break,
                "thesis_break_score": thesis_break_score,
                "ambiguity_score": ambiguity_score,
                "kill_path_score": kill_path_score,
                "wait_dominance_score": wait_dominance_score,
                "action_gap_bps": action_gap,
                "chosen_survival_ratio": chosen_survival_ratio,
                "dominant_failure_modes": dominant_failure_modes,
                "calibrated": calibration is not None,
            },
        )
