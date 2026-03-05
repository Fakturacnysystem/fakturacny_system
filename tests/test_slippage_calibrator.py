from __future__ import annotations

from autonomous_investment_robot.services.execution.slippage_calibrator import SlippageCalibrator


def test_slippage_calibration_updates_gate_safely() -> None:
    cal = SlippageCalibrator(
        percentile=0.95,
        min_bps=10.0,
        max_bps=60.0,
        default_spot_bps=15.0,
    )
    for i in range(200):
        # simulate adverse slippage between 5 and 45 bps
        cal.observe_bps(bps=5.0 + (i % 40), market="spot")
    out = cal.recalibrate(market="spot")

    assert out.samples >= 8
    assert 10.0 <= out.value_bps <= 60.0
    assert cal.calibrated_bps(market="spot") == out.value_bps


def test_calibration_respects_min_max_bounds() -> None:
    cal = SlippageCalibrator(
        percentile=0.95,
        min_bps=12.0,
        max_bps=18.0,
        default_spot_bps=15.0,
    )
    for _ in range(50):
        cal.observe_bps(bps=200.0, market="spot")
    out_hi = cal.recalibrate(market="spot")
    assert out_hi.value_bps == 18.0

    cal2 = SlippageCalibrator(
        percentile=0.95,
        min_bps=12.0,
        max_bps=18.0,
        default_spot_bps=15.0,
    )
    for _ in range(50):
        cal2.observe_bps(bps=0.5, market="spot")
    out_lo = cal2.recalibrate(market="spot")
    assert out_lo.value_bps == 12.0
