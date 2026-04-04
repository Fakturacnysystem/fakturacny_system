from datetime import datetime, timezone
from types import SimpleNamespace

from autonomous_investment_robot.services.calibration_service.service import CalibrationService
from autonomous_investment_robot.services.shadow_rival_service.service import ShadowRivalService
from autonomous_investment_robot.services.spre_service.service import SPREEngine


def test_spre_engine_prefers_no_trade_under_high_uncertainty_and_fragility():
    decision = SPREEngine().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        combined_signal=50.0,
        expected_edge_bps=6.0,
        expected_cost_bps=5.0,
        uncertainty=0.85,
        quantum_state=SimpleNamespace(
            collapse_decision=SimpleNamespace(
                expected_move_bps=2.0,
                no_trade_probability=0.8,
                execution_fragility_score=0.75,
            ),
        ),
        edge_immunity_decision=SimpleNamespace(
            report=SimpleNamespace(
                fragility_index=0.8,
                wait_value_score=4.0,
            ),
        ),
        profitability_context={"round_trip": {"recommended_size_multiplier": 0.4}},
    )

    assert decision.dominant_action == "no_trade"
    assert decision.heuristic is True
    assert decision.no_trade_quality > 0.0
    assert decision.metadata["chosen_survival_ratio"] >= 0.0
    assert "action_rankings" in decision.metadata
    assert "no_trade" in decision.metadata["action_rankings"]
    assert any(fork.name == "priced_in_fade" for fork in decision.forks)
    assert any(fork.name == "execution_reject_cluster" for fork in decision.forks)


def test_shadow_rival_service_vetoes_fragile_trade():
    spre_decision = SPREEngine().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        combined_signal=50.0,
        expected_edge_bps=12.0,
        expected_cost_bps=2.0,
        uncertainty=0.2,
        quantum_state=SimpleNamespace(
            collapse_decision=SimpleNamespace(
                expected_move_bps=15.0,
                no_trade_probability=0.85,
                execution_fragility_score=0.85,
            ),
        ),
        edge_immunity_decision=SimpleNamespace(
            report=SimpleNamespace(
                fragility_index=0.8,
                wait_value_score=1.0,
            ),
        ),
        profitability_context={"round_trip": {"recommended_size_multiplier": 0.9}},
    )

    report = ShadowRivalService().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        spre_decision=spre_decision,
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(no_trade_probability=0.85, execution_fragility_score=0.85)),
        edge_immunity_decision=SimpleNamespace(report=SimpleNamespace(fragility_index=0.8)),
    )

    assert report.action == "no_trade"
    assert report.allowed is False
    assert "shadow_rival_veto" in report.reasons or "spre_no_trade_dominant" in report.reasons
    assert float(report.metadata["kill_path_score"]) >= 0.0
    assert float(report.metadata["chosen_survival_ratio"]) >= 0.0


def test_spre_engine_uses_execution_simulation_and_event_risk():
    calibration = CalibrationService()
    calibration.update_from_episodes(
        [
            SimpleNamespace(realized_pnl=-10.0, failure_mode="execution_truth"),
            SimpleNamespace(realized_pnl=-5.0, failure_mode="execution"),
        ]
    )
    decision = SPREEngine(calibration_service=calibration).evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        combined_signal=40.0,
        expected_edge_bps=8.0,
        expected_cost_bps=3.0,
        uncertainty=0.35,
        quantum_state=SimpleNamespace(
            collapse_decision=SimpleNamespace(
                expected_move_bps=6.0,
                no_trade_probability=0.35,
                execution_fragility_score=0.45,
            ),
        ),
        edge_immunity_decision=SimpleNamespace(
            report=SimpleNamespace(
                fragility_index=0.5,
                wait_value_score=2.0,
            ),
        ),
        profitability_context={"round_trip": {"recommended_size_multiplier": 0.8}},
        event_intelligence_report=SimpleNamespace(overall_risk_score=0.7),
        synthetic_affect_state=SimpleNamespace(no_trade_threshold_shift=0.2),
        execution_simulation_report=SimpleNamespace(worst_case_cost_bps=9.0),
    )

    assert decision.dominant_action in {"wait", "no_trade", "trade_smaller"}
    assert any(fork.name == "integrity_break_reality" for fork in decision.forks)
    assert decision.metadata["calibrated"] is True
    assert float(decision.metadata["ambiguity_penalty"]) > 0.0
    assert isinstance(decision.metadata["dominant_failure_modes"], list)


def test_shadow_rival_service_uses_event_and_execution_break_signals():
    spre_decision = SPREEngine().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        combined_signal=30.0,
        expected_edge_bps=11.0,
        expected_cost_bps=2.0,
        uncertainty=0.25,
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(expected_move_bps=10.0, no_trade_probability=0.3, execution_fragility_score=0.4)),
        edge_immunity_decision=SimpleNamespace(report=SimpleNamespace(fragility_index=0.45, wait_value_score=1.0)),
        profitability_context={"round_trip": {"recommended_size_multiplier": 0.9}},
    )

    report = ShadowRivalService().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        spre_decision=spre_decision,
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(no_trade_probability=0.3, execution_fragility_score=0.4)),
        edge_immunity_decision=SimpleNamespace(report=SimpleNamespace(fragility_index=0.45)),
        event_intelligence_report=SimpleNamespace(overall_risk_score=0.85),
        synthetic_affect_state=SimpleNamespace(stress=0.9, fear=0.7),
        execution_simulation_report=SimpleNamespace(recommended_action="no_trade"),
    )

    assert report.action == "no_trade"
    assert report.allowed is False
    assert "adversarial_event_cluster" in report.reasons or "shadow_execution_break" in report.reasons
    assert float(report.metadata["thesis_break_score"]) > 0.0
    assert float(report.metadata["ambiguity_score"]) >= 0.0
    assert isinstance(report.metadata["dominant_failure_modes"], list)


def test_spre_engine_collapses_probe_selection_to_trade_smaller():
    decision = SPREEngine().evaluate(
        symbol="BTCUSDT",
        ts=datetime.now(timezone.utc),
        combined_signal=20.0,
        expected_edge_bps=12.0,
        expected_cost_bps=8.0,
        uncertainty=0.45,
        quantum_state=SimpleNamespace(
            collapse_decision=SimpleNamespace(
                expected_move_bps=5.0,
                no_trade_probability=0.05,
                execution_fragility_score=0.05,
                branch_disagreement_score=0.45,
                scenario_drift_score=0.3,
            ),
        ),
        edge_immunity_decision=SimpleNamespace(
            report=SimpleNamespace(
                fragility_index=0.05,
                wait_value_score=0.2,
            ),
        ),
        profitability_context={"round_trip": {"recommended_size_multiplier": 0.8}},
    )

    assert decision.dominant_action == "trade_smaller"
    assert decision.metadata["internal_action"] == "probe"
    assert decision.size_multiplier == 0.25
    assert "probe_entry_dominant" in decision.reasons


def test_spre_engine_prefers_bounded_probe_when_edge_survives_and_ambiguity_is_not_adverse():
    decision = SPREEngine().evaluate(
        symbol="SOL/EUR",
        ts=datetime.now(timezone.utc),
        combined_signal=14.0,
        expected_edge_bps=53.59918780936158,
        expected_cost_bps=38.952125971379196,
        uncertainty=0.5461867401305002,
        quantum_state=SimpleNamespace(
            collapse_decision=SimpleNamespace(
                expected_move_bps=1237.1157462604012,
                no_trade_probability=0.3938570023380764,
                execution_fragility_score=0.34046422402702964,
                branch_disagreement_score=0.717977563431909,
                scenario_drift_score=0.7318755987183742,
            ),
        ),
        edge_immunity_decision=SimpleNamespace(
            report=SimpleNamespace(
                fragility_index=0.20094846277861933,
                wait_value_score=0.1,
            ),
        ),
        profitability_context={"round_trip": {"recommended_size_multiplier": 1.0}},
        synthetic_affect_state=SimpleNamespace(no_trade_threshold_shift=0.05238728109018716),
        execution_simulation_report=SimpleNamespace(worst_case_cost_bps=2.601377199695287),
    )

    assert decision.dominant_action == "trade_smaller"
    assert decision.metadata["internal_action"] in {"probe", "trade_smaller"}
    assert 0.0 < decision.size_multiplier <= 0.5


def test_calibration_service_emits_spre_and_shadow_bias_metadata():
    calibration = CalibrationService()
    profile = calibration.update_from_episodes(
        [
            SimpleNamespace(realized_pnl=-25.0, failure_mode="execution_truth_event"),
            SimpleNamespace(realized_pnl=-10.0, failure_mode="event"),
            SimpleNamespace(realized_pnl=5.0, failure_mode=""),
        ]
    )

    assert profile.metadata["shadow_veto_bias"] > 0.0
    assert profile.metadata["spre_wait_bias"] > 0.0
    assert profile.metadata["dominance_caution_bias"] > 0.0
