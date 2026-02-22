from autonomous_investment_robot.services.mlops.service import MLOpsService


def test_canary_rollback_drift_trigger():
    m = MLOpsService(rollback_dd_threshold_pct=2.0, drift_psi_threshold=0.2)
    psi = m.detector.psi([1, 1, 1], [2, 2, 2])
    assert m.should_rollback(drawdown_pct=3.0, psi_value=psi) is True


def test_canary_budget_split():
    m = MLOpsService(rollback_dd_threshold_pct=2.0, drift_psi_threshold=0.2)
    assert m.canary_risk_budget(1000, 0.05) == 50


def test_model_registry_register_hash_and_promote():
    m = MLOpsService(rollback_dd_threshold_pct=2.0, drift_psi_threshold=0.2)
    rec = m.register_model(
        "canary-v1",
        metrics={"net_after_costs_bps": 4.2, "drawdown_pct": 1.0},
        canary=True,
        metadata={"features": ["a", "b"], "train_window": "2025-01"},
    )
    assert rec.canary is True
    assert len(rec.artifact_hash) == 64
    promoted = m.promote_canary("canary-v1")
    assert promoted.canary is False
    assert promoted.promoted is True
    assert m.registry.latest_stable().version == "canary-v1"


def test_compare_canary_promote_when_net_after_costs_better_and_risk_not_worse():
    m = MLOpsService(rollback_dd_threshold_pct=2.0, drift_psi_threshold=0.2)
    cmp = m.compare_canary(
        baseline_metrics={"net_after_costs_bps": 3.0, "drawdown_pct": 1.2, "slippage_bps": 1.5, "funding_paid_pct": 0.10},
        canary_metrics={"net_after_costs_bps": 4.0, "drawdown_pct": 1.3, "slippage_bps": 1.7, "funding_paid_pct": 0.12},
        psi_value=0.1,
    )
    assert cmp.promote is True
    assert cmp.rollback is False
    assert cmp.reason == "promote_canary"


def test_compare_canary_rolls_back_on_drift_or_dd():
    m = MLOpsService(rollback_dd_threshold_pct=2.0, drift_psi_threshold=0.2)
    cmp = m.compare_canary(
        baseline_metrics={"net_after_costs_bps": 5.0, "drawdown_pct": 1.0, "slippage_bps": 1.0, "funding_paid_pct": 0.05},
        canary_metrics={"net_after_costs_bps": 3.5, "drawdown_pct": 2.0, "slippage_bps": 1.3, "funding_paid_pct": 0.08},
        psi_value=0.3,
    )
    assert cmp.promote is False
    assert cmp.rollback is True
    assert cmp.reason == "rollback_canary"


def test_compare_canary_hold_when_mixed_signals():
    m = MLOpsService(rollback_dd_threshold_pct=2.0, drift_psi_threshold=0.2)
    cmp = m.compare_canary(
        baseline_metrics={"net_after_costs_bps": 3.0, "drawdown_pct": 1.0, "slippage_bps": 1.0, "funding_paid_pct": 0.05},
        canary_metrics={"net_after_costs_bps": 3.1, "drawdown_pct": 1.4, "slippage_bps": 2.5, "funding_paid_pct": 0.20},
        psi_value=0.1,
    )
    assert cmp.promote is False
    assert cmp.rollback is False
    assert cmp.reason == "hold_canary"


def test_deployment_action_throttle_and_safe_mode():
    m = MLOpsService(rollback_dd_threshold_pct=2.0, drift_psi_threshold=0.2)
    a1 = m.deployment_action(drawdown_pct=1.0, psi_value=0.1, performance_drift=0.08)
    assert a1.action == "throttle"
    a2 = m.deployment_action(drawdown_pct=1.0, psi_value=0.25, performance_drift=0.0)
    assert a2.action == "safe_mode"
