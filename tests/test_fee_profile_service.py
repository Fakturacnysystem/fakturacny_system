from __future__ import annotations

from autonomous_investment_robot.services.fees.fee_profile import FeeProfileService


class _SpotConnector:
    def __init__(self) -> None:
        self.calls = 0

    def trade_volume(self, pair: str | None = None, fee_info: bool = True) -> dict:
        _ = fee_info
        self.calls += 1
        key = pair or "XBTUSD"
        return {
            "result": {
                "volume": "12345.0",
                "fees": {key: {"fee": "0.26"}},
                "fees_maker": {key: {"fee": "0.16"}},
            }
        }


def test_fee_profile_refresh_from_trade_volume() -> None:
    spot = _SpotConnector()
    svc = FeeProfileService(
        connector_spot=spot,
        default_entry_fee_bps=30.0,
        default_exit_fee_bps=30.0,
        refresh_interval_s=1.0,
    )

    profile = svc.refresh(pair="XBTUSD", force=True)

    assert profile.source == "spot_trade_volume"
    assert profile.spot_taker_fee_bps >= 26.0
    assert profile.spot_maker_fee_bps >= 16.0
    assert profile.spot_worst_case_bps >= 26.0
    assert profile.trade_volume_quote == 12345.0


def test_fee_profile_volume_jump_triggers_refresh() -> None:
    spot = _SpotConnector()
    svc = FeeProfileService(
        connector_spot=spot,
        refresh_interval_s=9999.0,
        volume_jump_ratio=0.10,
    )
    svc.refresh(pair="XBTUSD", force=True, trade_volume_hint=1000.0)
    before_calls = spot.calls

    _ = svc.maybe_refresh(pair="XBTUSD", trade_volume_hint=20000.0)

    assert spot.calls > before_calls


def test_fee_profile_liquidity_role_classification() -> None:
    svc = FeeProfileService()

    assert (
        svc.classify_liquidity_role(
            fill_payload={"liquidity": "maker"},
            order_payload={},
        )
        == "maker"
    )
    assert (
        svc.classify_liquidity_role(
            fill_payload={},
            order_payload={"oflags": "post"},
        )
        == "maker"
    )
    assert (
        svc.classify_liquidity_role(
            fill_payload={},
            order_payload={"ordertype": "market"},
        )
        == "taker"
    )
