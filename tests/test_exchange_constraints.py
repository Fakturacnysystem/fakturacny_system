from __future__ import annotations

from autonomous_investment_robot.services.exchange_constraints import ExchangeConstraintsOracle


class _FakeConnector:
    def asset_pairs(self):
        return {
            "XBTUSD": {
                "altname": "XBTUSD",
                "wsname": "XBT/USD",
                "ordermin": "0.0001",
                "costmin": "8.0",
                "pair_decimals": 1,
                "lot_decimals": 8,
                "ordertype": ["market", "limit"],
            }
        }

    def ticker(self, pair=None):  # noqa: ARG002
        return {"XBTUSD": {"b": ["50000.0"], "a": ["50010.0"]}}


def test_constraints_oracle_get_and_persist(tmp_path):
    svc = ExchangeConstraintsOracle(_FakeConnector(), run_dir=str(tmp_path), ttl_s=1800)
    c = svc.get_constraints("XBTUSD")
    assert c.min_base_qty == 0.0001
    assert c.price_precision == 1
    assert c.qty_precision == 8
    assert c.min_quote_notional >= 8.0
    assert (tmp_path / "exchange_constraints.json").exists()


def test_validate_and_round_respects_min_notional_and_precision(tmp_path):
    svc = ExchangeConstraintsOracle(_FakeConnector(), run_dir=str(tmp_path), ttl_s=1800)
    ok, out = svc.validate_and_round_order(
        symbol="XBTUSD",
        side="buy",
        notional_quote=1.0,  # below min -> clamp to min_quote_notional
        bid=50000.0,
        ask=50010.0,
        order_type="market",
        max_quote_notional=50.0,
    )
    assert ok is True
    assert not isinstance(out, str)
    assert out.rounded_notional_quote >= out.min_quote_notional
    assert out.rounded_price > 0.0
    assert out.rounded_qty > 0.0


def test_validate_and_round_rejects_invalid_inputs(tmp_path):
    svc = ExchangeConstraintsOracle(_FakeConnector(), run_dir=str(tmp_path), ttl_s=1800)
    ok, reason = svc.validate_and_round_order(
        symbol="XBTUSD",
        side="buy",
        notional_quote=10.0,
        bid=0.0,
        ask=50010.0,
    )
    assert ok is False
    assert reason == "invalid_book"
