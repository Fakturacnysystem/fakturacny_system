from __future__ import annotations

from autonomous_investment_robot.services.multi_account.account_router import AccountRouter


def test_account_router_round_robin(monkeypatch) -> None:
    monkeypatch.setenv("KRKN_API_KEY_MAIN", "k1")
    monkeypatch.setenv("KRKN_API_KEY_SUB1", "k2")
    r = AccountRouter(strategy="round_robin")
    a1 = r.choose_account(symbol="XBTUSD")
    a2 = r.choose_account(symbol="XBTUSD")
    assert a1.account_id != a2.account_id


def test_account_router_liquidity_based(monkeypatch) -> None:
    monkeypatch.setenv("KRKN_API_KEY_MAIN", "k1")
    monkeypatch.setenv("KRKN_API_KEY_SUB1", "k2")
    r = AccountRouter(strategy="liquidity_based")
    dec = r.choose_account(
        symbol="ETHEUR",
        available_margin_by_account={"main": 10.0, "sub1": 100.0},
        rate_limit_pressure_by_account={"main": 0.0, "sub1": 1.0},
    )
    assert dec.account_id == "sub1"
