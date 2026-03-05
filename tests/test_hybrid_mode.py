from __future__ import annotations

from autonomous_investment_robot.services.execution.hybrid_mode import parse_hybrid_symbols, symbol_live_in_hybrid


def test_parse_hybrid_symbols_json(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMOUS_HYBRID_SYMBOLS", '["XBTUSD","ETHEUR"]')
    out = parse_hybrid_symbols()
    assert "XBTUSD" in out
    assert "ETHEUR" in out


def test_symbol_live_in_hybrid_default_true_when_empty() -> None:
    assert symbol_live_in_hybrid("XBTUSD", set()) is True
    assert symbol_live_in_hybrid("XBTUSD", {"ETHEUR"}) is False
