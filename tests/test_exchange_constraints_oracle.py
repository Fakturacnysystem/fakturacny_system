from __future__ import annotations

from autonomous_investment_robot.services.exchange_constraints import ExchangeConstraintsOracle


class _FakeConnector:
    def asset_pairs(self):
        return {
            "XBTEUR": {
                "altname": "XBTEUR",
                "wsname": "XBT/EUR",
                "ordermin": "0.0001",
                "costmin": "8.0",
                "pair_decimals": 2,
                "lot_decimals": 8,
                "ordertype": ["limit", "market"],
            }
        }

    def ticker(self, pair=None):  # noqa: ARG002
        return {"XBTEUR": {"b": ["60000.0"], "a": ["60010.0"]}}


def test_effective_min_quote_is_max_of_exchange_and_user_floor(tmp_path):
    svc = ExchangeConstraintsOracle(_FakeConnector(), run_dir=str(tmp_path), ttl_s=1800)
    exchange_min = svc.get("XBTEUR").min_quote_notional
    eff = svc.effective_min_quote("XBTEUR", user_floor=22.0)
    assert eff >= 22.0
    assert eff >= exchange_min


def test_validate_and_round_enforces_min_notional_and_precision(tmp_path):
    svc = ExchangeConstraintsOracle(_FakeConnector(), run_dir=str(tmp_path), ttl_s=1800)
    ok, reason, payload = svc.validate_and_round(
        symbol="XBTEUR",
        side="buy",
        target_notional_quote=1.0,
        bid=60000.0,
        ask=60010.0,
        user_floor=12.5,
    )
    assert ok is True
    assert reason == "ok"
    assert payload["rounded_notional_quote"] >= payload["effective_min_notional_quote"] >= 12.5
    assert payload["order_price"] > 0.0
    assert payload["order_qty"] > 0.0

