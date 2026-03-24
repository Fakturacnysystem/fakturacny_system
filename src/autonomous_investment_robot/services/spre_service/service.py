from __future__ import annotations

from collections import Counter
from typing import Any

from autonomous_investment_robot.core.contracts import ActionEvaluation, RealityFork, SPREDecision


class SPREEngine:
    _ACTIONS = ("trade_now", "trade_smaller", "probe", "wait", "no_trade")

    def __init__(self, calibration_service: object | None = None) -> None:
        self.calibration_service = calibration_service

    def _normalize_forks(self, forks: list[RealityFork]) -> list[RealityFork]:
        total = sum(max(0.0, float(fork.probability)) for fork in forks)
        if total <= 0.0:
            equal = 1.0 / max(len(forks), 1)
            return [RealityFork(**{**fork.__dict__, "probability": equal}) for fork in forks]
        return [RealityFork(**{**fork.__dict__, "probability": max(0.0, float(fork.probability)) / total}) for fork in forks]

    def _forks(
        self,
        *,
        expected_move_bps: float,
        uncertainty: float,
        fragility: float,
        no_trade_probability: float,
        event_risk: float,
        simulated_cost_bps: float,
        branch_disagreement: float,
        scenario_drift: float,
        wait_value: float,
    ) -> list[RealityFork]:
        adverse_probability = 0.14 + uncertainty * 0.08 + fragility * 0.06 + branch_disagreement * 0.05
        integrity_probability = 0.05 + event_risk * 0.10 + scenario_drift * 0.05
        delayed_probability = 0.04 + uncertainty * 0.06 + max(simulated_cost_bps, 0.0) / 180.0
        liquidity_probability = 0.05 + fragility * 0.08 + simulated_cost_bps / 220.0
        crowding_probability = 0.03 + no_trade_probability * 0.06 + branch_disagreement * 0.05
        recovery_probability = 0.08 + max(0.0, 0.16 - uncertainty * 0.05 - event_risk * 0.05)
        mean_reversion_probability = 0.05 + max(wait_value, 0.0) / 35.0 + scenario_drift * 0.03
        priced_in_probability = 0.04 + event_risk * 0.04 + branch_disagreement * 0.03
        simulation_break_probability = 0.03 + simulated_cost_bps / 220.0 + fragility * 0.04
        stale_signal_probability = 0.03 + uncertainty * 0.04 + scenario_drift * 0.04
        squeeze_extension_probability = 0.03 + max(0.0, expected_move_bps) / 220.0 + (1.0 - min(1.0, uncertainty)) * 0.02
        base_probability = max(
            0.06,
            1.0
            - adverse_probability
            - integrity_probability
            - delayed_probability
            - liquidity_probability
            - crowding_probability
            - recovery_probability
            - mean_reversion_probability
            - priced_in_probability
            - simulation_break_probability
            - stale_signal_probability
            - squeeze_extension_probability,
        )
        forks = [
            RealityFork(
                name="base_case",
                probability=base_probability,
                edge_adjustment_bps=expected_move_bps * 0.20,
                execution_cost_penalty_bps=fragility * 2.2,
                dominant_failure_mode="none",
                metadata={"wait_bonus": 0.0, "avoid_loss_bonus": 0.0},
            ),
            RealityFork(
                name="adverse_follow_through",
                probability=adverse_probability,
                edge_adjustment_bps=-max(4.0, abs(expected_move_bps) * 0.70 + no_trade_probability * 5.5),
                execution_cost_penalty_bps=4.5 + fragility * 5.5,
                dominant_failure_mode="adverse_follow_through",
                metadata={"wait_bonus": 1.0, "avoid_loss_bonus": 2.0},
            ),
            RealityFork(
                name="integrity_break_reality",
                probability=integrity_probability,
                edge_adjustment_bps=-max(3.5, abs(expected_move_bps) * 0.42 + event_risk * 6.5),
                execution_cost_penalty_bps=max(2.0, simulated_cost_bps * 0.5 + fragility * 2.5),
                dominant_failure_mode="integrity_break",
                metadata={"wait_bonus": 1.6, "avoid_loss_bonus": 2.5},
            ),
            RealityFork(
                name="delayed_fill_decay",
                probability=delayed_probability,
                edge_adjustment_bps=max(-6.0, expected_move_bps * 0.06),
                execution_cost_penalty_bps=max(1.5, simulated_cost_bps * 0.85 + fragility * 2.1),
                dominant_failure_mode="delayed_fill_decay",
                metadata={"wait_bonus": 1.8, "avoid_loss_bonus": 1.3},
            ),
            RealityFork(
                name="liquidity_vacuum",
                probability=liquidity_probability,
                edge_adjustment_bps=-max(2.5, abs(expected_move_bps) * 0.30 + simulated_cost_bps * 0.35),
                execution_cost_penalty_bps=max(3.0, simulated_cost_bps * 0.95 + fragility * 3.0),
                dominant_failure_mode="liquidity_vacuum",
                metadata={"wait_bonus": 1.8, "avoid_loss_bonus": 2.0},
            ),
            RealityFork(
                name="crowding_unwind",
                probability=crowding_probability,
                edge_adjustment_bps=-max(2.5, abs(expected_move_bps) * 0.24 + branch_disagreement * 4.2),
                execution_cost_penalty_bps=max(1.5, fragility * 2.4 + branch_disagreement * 2.1),
                dominant_failure_mode="crowding_unwind",
                metadata={"wait_bonus": 0.8, "avoid_loss_bonus": 1.5},
            ),
            RealityFork(
                name="recovery_reality",
                probability=recovery_probability,
                edge_adjustment_bps=max(1.0, abs(expected_move_bps) * 0.32),
                execution_cost_penalty_bps=max(0.5, fragility * 1.4),
                dominant_failure_mode="late_confirmation",
                metadata={"wait_bonus": 0.6, "avoid_loss_bonus": 0.2},
            ),
            RealityFork(
                name="mean_reversion_wait_window",
                probability=mean_reversion_probability,
                edge_adjustment_bps=max(0.0, wait_value * 0.6 - abs(expected_move_bps) * 0.08),
                execution_cost_penalty_bps=max(0.5, fragility * 1.2),
                dominant_failure_mode="timing_mismatch",
                metadata={"wait_bonus": 2.5, "avoid_loss_bonus": 0.6},
            ),
            RealityFork(
                name="priced_in_fade",
                probability=priced_in_probability,
                edge_adjustment_bps=-max(1.5, abs(expected_move_bps) * 0.18 + event_risk * 3.0),
                execution_cost_penalty_bps=max(0.8, fragility * 1.0 + simulated_cost_bps * 0.18),
                dominant_failure_mode="priced_in_fade",
                metadata={"wait_bonus": 1.0, "avoid_loss_bonus": 1.0},
            ),
            RealityFork(
                name="execution_reject_cluster",
                probability=simulation_break_probability,
                edge_adjustment_bps=-max(2.0, simulated_cost_bps * 0.25),
                execution_cost_penalty_bps=max(3.5, simulated_cost_bps * 1.15 + fragility * 2.0),
                dominant_failure_mode="execution_break",
                metadata={"wait_bonus": 1.6, "avoid_loss_bonus": 2.1},
            ),
            RealityFork(
                name="stale_signal_chop",
                probability=stale_signal_probability,
                edge_adjustment_bps=-max(1.5, abs(expected_move_bps) * 0.15 + scenario_drift * 2.0),
                execution_cost_penalty_bps=max(0.8, fragility * 1.2),
                dominant_failure_mode="stale_signal",
                metadata={"wait_bonus": 1.4, "avoid_loss_bonus": 1.0},
            ),
            RealityFork(
                name="squeeze_extension",
                probability=squeeze_extension_probability,
                edge_adjustment_bps=max(0.8, expected_move_bps * 0.28),
                execution_cost_penalty_bps=max(0.8, fragility * 1.3),
                dominant_failure_mode="late_chase",
                metadata={"wait_bonus": 0.2, "avoid_loss_bonus": 0.1},
            ),
        ]
        return self._normalize_forks(forks)

    def _action_utility(
        self,
        *,
        action: str,
        fork: RealityFork,
        base_edge: float,
        no_trade_quality: float,
        wait_value: float,
        ambiguity_penalty: float,
        learning_value: float,
    ) -> float:
        wait_bonus = float(fork.metadata.get("wait_bonus", 0.0) or 0.0)
        avoid_loss_bonus = float(fork.metadata.get("avoid_loss_bonus", 0.0) or 0.0)
        if action == "trade_now":
            return base_edge + fork.edge_adjustment_bps - fork.execution_cost_penalty_bps - ambiguity_penalty * 2.7
        if action == "trade_smaller":
            return (base_edge * 0.64) + (fork.edge_adjustment_bps * 0.56) - (fork.execution_cost_penalty_bps * 0.50) - ambiguity_penalty * 1.1
        if action == "probe":
            return (base_edge * 0.20) + (fork.edge_adjustment_bps * 0.30) - (fork.execution_cost_penalty_bps * 0.18) + learning_value - ambiguity_penalty * 0.25
        if action == "wait":
            return wait_value + wait_bonus - max(0.0, base_edge) * 0.20 - ambiguity_penalty * 0.12
        return no_trade_quality + avoid_loss_bonus

    def evaluate(
        self,
        *,
        symbol: str,
        ts: object,
        combined_signal: float,
        expected_edge_bps: float,
        expected_cost_bps: float,
        uncertainty: float,
        quantum_state: object | None = None,
        edge_immunity_decision: object | None = None,
        profitability_context: dict | None = None,
        event_intelligence_report: object | None = None,
        synthetic_affect_state: object | None = None,
        execution_simulation_report: object | None = None,
    ) -> SPREDecision:
        calibration = self.calibration_service.current_profile() if self.calibration_service is not None else None
        calibration_meta = {} if calibration is None else dict(getattr(calibration, "metadata", {}) or {})
        collapse = getattr(quantum_state, "collapse_decision", object()) if quantum_state is not None else object()
        edge_report = getattr(edge_immunity_decision, "report", object()) if edge_immunity_decision is not None else object()
        expected_move_bps = float(getattr(collapse, "expected_move_bps", 0.0) or 0.0)
        no_trade_probability = float(getattr(collapse, "no_trade_probability", 0.0) or 0.0)
        branch_disagreement = float(getattr(collapse, "branch_disagreement_score", 0.0) or 0.0)
        scenario_drift = float(getattr(collapse, "scenario_drift_score", 0.0) or 0.0)
        fragility = max(
            float(getattr(collapse, "execution_fragility_score", 0.0) or 0.0),
            float(getattr(edge_report, "fragility_index", 0.0) or 0.0),
        )
        if calibration is not None:
            no_trade_probability = min(1.0, no_trade_probability + float(getattr(calibration, "no_trade_bias", 0.0) or 0.0))
            fragility = min(1.0, fragility + float(getattr(calibration, "fragility_bias", 0.0) or 0.0))
        wait_value = float(getattr(edge_report, "wait_value_score", 0.0) or 0.0) + float(calibration_meta.get("spre_wait_bias", 0.0) or 0.0) * 4.0
        round_trip = {} if profitability_context is None else dict(profitability_context.get("round_trip", {}))
        recommended_size = float(round_trip.get("recommended_size_multiplier", 1.0) or 1.0)
        if calibration is not None:
            recommended_size = min(recommended_size, float(getattr(calibration, "size_bias", 1.0) or 1.0))
        base_edge = float(expected_edge_bps) - float(expected_cost_bps)
        event_risk = 0.0 if event_intelligence_report is None else float(getattr(event_intelligence_report, "overall_risk_score", 0.0) or 0.0)
        affect_shift = 0.0 if synthetic_affect_state is None else float(getattr(synthetic_affect_state, "no_trade_threshold_shift", 0.0) or 0.0)
        simulated_cost_bps = 0.0 if execution_simulation_report is None else float(getattr(execution_simulation_report, "worst_case_cost_bps", 0.0) or 0.0)
        ambiguity_penalty = max(uncertainty + affect_shift, branch_disagreement, scenario_drift, event_risk * 0.8) + float(calibration_meta.get("dominance_caution_bias", 0.0) or 0.0)
        learning_value = max(0.0, min(2.8, uncertainty * 1.5 + branch_disagreement * 1.1 + scenario_drift * 0.9))
        no_trade_quality = max(
            no_trade_probability * 8.0,
            ambiguity_penalty * 7.4,
            fragility * 8.7,
            event_risk * 6.9,
            simulated_cost_bps * 0.40,
        )
        forks = self._forks(
            expected_move_bps=expected_move_bps,
            uncertainty=uncertainty,
            fragility=fragility,
            no_trade_probability=no_trade_probability,
            event_risk=event_risk,
            simulated_cost_bps=simulated_cost_bps,
            branch_disagreement=branch_disagreement,
            scenario_drift=scenario_drift,
            wait_value=wait_value,
        )

        raw_metrics: dict[str, dict[str, Any]] = {}
        for action in self._ACTIONS:
            scenario_utilities: list[float] = []
            for fork in forks:
                scenario_utilities.append(
                    self._action_utility(
                        action=action,
                        fork=fork,
                        base_edge=base_edge,
                        no_trade_quality=no_trade_quality,
                        wait_value=wait_value,
                        ambiguity_penalty=ambiguity_penalty,
                        learning_value=learning_value,
                    )
                )
            expected_utility = sum(fork.probability * utility for fork, utility in zip(forks, scenario_utilities))
            worst_case = min(scenario_utilities)
            survival_ratio = sum(fork.probability for fork, utility in zip(forks, scenario_utilities) if utility > 0.0)
            failure_counter = Counter(
                fork.dominant_failure_mode for fork, utility in zip(forks, scenario_utilities) if utility <= 0.0 and fork.dominant_failure_mode != "none"
            )
            raw_metrics[action] = {
                "scenario_utilities": scenario_utilities,
                "expected_utility": expected_utility,
                "worst_case": worst_case,
                "survival_ratio": survival_ratio,
                "failure_modes": [item for item, _ in failure_counter.most_common(4)],
            }

        best_expected = max(metric["expected_utility"] for metric in raw_metrics.values())
        dominance_scores: dict[str, float] = {}
        evaluations: list[ActionEvaluation] = []
        for action, metric in raw_metrics.items():
            regret = max(0.0, best_expected - float(metric["expected_utility"]))
            dominance = (
                float(metric["expected_utility"]) * 0.52
                + float(metric["worst_case"]) * 0.12
                + float(metric["survival_ratio"]) * max(4.0, abs(base_edge) * 0.30)
                - regret * 0.25
            )
            if action == "no_trade":
                dominance += no_trade_quality * 0.10
            elif action == "wait":
                dominance += wait_value * 0.26
            elif action == "probe":
                dominance += learning_value * 0.45
            dominance_scores[action] = dominance

        action_rankings = [name for name, _ in sorted(dominance_scores.items(), key=lambda item: item[1], reverse=True)]
        for action, metric in raw_metrics.items():
            regret = max(0.0, best_expected - float(metric["expected_utility"]))
            reasons: list[str] = []
            if action == "no_trade":
                reasons.append("no_trade_quality_dominant")
            elif action == "wait":
                reasons.append("wait_for_clearer_reality")
            elif action == "probe":
                reasons.append("probe_entry_optionality")
            elif action == "trade_smaller":
                reasons.append("reduced_regret_trade")
            else:
                reasons.append("trade_edge_survives_forks")
            if simulated_cost_bps > max(base_edge, 0.0):
                reasons.append("execution_simulation_cost_pressure")
            if event_risk >= 0.6:
                reasons.append("event_risk_pressure")
            if ambiguity_penalty >= 0.6:
                reasons.append("ambiguity_penalty_high")
            evaluations.append(
                ActionEvaluation(
                    action=action,
                    expected_utility_bps=float(metric["expected_utility"]),
                    worst_case_bps=float(metric["worst_case"]),
                    regret_bps=regret,
                    reasons=sorted(set(reasons)),
                    metadata={
                        "survival_ratio": float(metric["survival_ratio"]),
                        "dominance_score": float(dominance_scores[action]),
                        "dominant_failure_modes": list(metric["failure_modes"]),
                        "ranking_index": action_rankings.index(action),
                    },
                )
            )

        evaluations.sort(key=lambda item: float(item.metadata.get("dominance_score", item.expected_utility_bps)), reverse=True)
        by_action = {evaluation.action: evaluation for evaluation in evaluations}
        selected = evaluations[0]
        probe_eval = by_action.get("probe")
        if (
            probe_eval is not None
            and selected.action in {"trade_now", "trade_smaller"}
            and float(probe_eval.expected_utility_bps) >= float(selected.expected_utility_bps) - 1.25
            and learning_value >= 0.70
            and ambiguity_penalty >= 0.35
            and no_trade_quality < float(selected.expected_utility_bps) * 1.25
        ):
            selected = probe_eval
        elif (
            probe_eval is not None
            and selected.action == "no_trade"
            and float(probe_eval.metadata.get("dominance_score", 0.0) or 0.0) >= float(selected.metadata.get("dominance_score", 0.0) or 0.0) - 2.50
            and no_trade_probability < 0.25
            and event_risk < 0.35
            and fragility < 0.35
            and branch_disagreement >= 0.30
            and learning_value >= 0.90
        ):
            selected = probe_eval
        runner_candidates = [evaluation for evaluation in evaluations if evaluation.action != selected.action]
        runner_up = runner_candidates[0] if runner_candidates else selected
        dominant = selected
        internal_action = dominant.action
        final_action = internal_action
        size_multiplier = 1.0
        chosen_survival_ratio = float(dominant.metadata.get("survival_ratio", 0.0) or 0.0)
        action_gap = float(dominant.metadata.get("dominance_score", 0.0) or 0.0) - float(runner_up.metadata.get("dominance_score", 0.0) or 0.0)
        dominant_failure_modes = list(dominant.metadata.get("dominant_failure_modes", []) or [])
        reasons = list(dominant.reasons)

        if internal_action == "probe":
            final_action = "trade_smaller"
            size_multiplier = min(0.25, recommended_size)
            reasons.append("probe_entry_dominant")
        elif internal_action == "trade_smaller":
            size_multiplier = min(0.5, recommended_size)
        elif internal_action in {"wait", "no_trade"}:
            size_multiplier = 0.0
        else:
            size_multiplier = max(0.25, min(1.0, recommended_size))

        if final_action in {"trade_now", "trade_smaller"} and chosen_survival_ratio < 0.38 and no_trade_quality >= dominant.expected_utility_bps * 0.80:
            final_action = "no_trade"
            size_multiplier = 0.0
            reasons.append("survival_ratio_too_low")
        elif final_action in {"trade_now", "trade_smaller"} and action_gap < 1.25 and ambiguity_penalty >= 0.55:
            final_action = "wait"
            size_multiplier = 0.0
            reasons.append("dominance_gap_too_small")
        elif final_action == "trade_now" and wait_value > dominant.expected_utility_bps and fragility >= 0.45:
            final_action = "wait"
            size_multiplier = 0.0
            reasons.append("wait_dominates_trade_now")
        elif final_action == "trade_now" and event_risk >= 0.75 and branch_disagreement >= 0.55:
            final_action = "trade_smaller"
            size_multiplier = min(size_multiplier, 0.35)
            reasons.append("event_ambiguity_forces_smaller")

        side = None if abs(combined_signal) < 1e-9 else ("buy" if combined_signal > 0 else "sell")
        narrative = (
            f"dominant_action={final_action}; internal_action={internal_action}; base_edge_bps={base_edge:.2f}; "
            f"no_trade_quality={no_trade_quality:.2f}; survival_ratio={chosen_survival_ratio:.2f}; "
            f"dominance_gap={action_gap:.2f}; worst_case_bps={dominant.worst_case_bps:.2f}"
        )
        return SPREDecision(
            symbol=symbol,
            ts=ts,  # type: ignore[arg-type]
            dominant_action=final_action,
            side=side,
            size_multiplier=size_multiplier,
            regret_score=dominant.regret_bps,
            no_trade_quality=no_trade_quality,
            narrative=narrative,
            action_evaluations=evaluations,
            forks=forks,
            reasons=sorted(set(reasons)),
            heuristic=True,
            metadata={
                "base_edge_bps": base_edge,
                "wait_value_score": wait_value,
                "fragility": fragility,
                "event_risk": event_risk,
                "simulated_cost_bps": simulated_cost_bps,
                "ambiguity_penalty": ambiguity_penalty,
                "learning_value": learning_value,
                "dominance_scores": dominance_scores,
                "action_rankings": action_rankings,
                "action_universe": list(self._ACTIONS),
                "chosen_survival_ratio": chosen_survival_ratio,
                "action_gap_bps": action_gap,
                "dominant_failure_modes": dominant_failure_modes,
                "probe_entry_selected": internal_action == "probe",
                "internal_action": internal_action,
                "branch_disagreement": branch_disagreement,
                "scenario_drift": scenario_drift,
                "calibrated": calibration is not None,
            },
        )
