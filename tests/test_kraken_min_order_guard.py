from autonomous_investment_robot.services.execution.live_kraken_spot_service import KrakenMinOrderGuard


class _Dummy:
    def asset_pairs(self):
        return {"XBTUSD": {"ordermin": "0.01", "pair_decimals": 1, "lot_decimals": 2}}


def test_min_order_guard_blocks_small_qty():
    g = KrakenMinOrderGuard(_Dummy())
    ok, reason = g.validate("XBTUSD", volume=0.001, price=100.0, available_quote=1000.0)
    assert ok is False
    assert reason == "min_order_block"
