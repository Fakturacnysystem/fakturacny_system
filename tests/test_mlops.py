from autonomous_investment_robot.services.mlops.service import MLOpsService


def test_canary_rollback_drift_trigger():
    m = MLOpsService(rollback_dd_threshold_pct=2.0, drift_psi_threshold=0.2)
    psi = m.detector.psi([1, 1, 1], [2, 2, 2])
    assert m.should_rollback(drawdown_pct=-3.0, psi_value=psi) is True
