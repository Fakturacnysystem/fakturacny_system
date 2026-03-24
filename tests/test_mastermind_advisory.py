from types import SimpleNamespace

from autonomous_investment_robot.services.mastermind.service import MastermindService


def test_mastermind_noop_returns_none(monkeypatch):
    monkeypatch.setenv("ADVISORY_PROVIDER", "noop")
    svc = MastermindService()

    result = svc.advise("BTCUSDT", {"ret_1": 0.01}, "trend")

    assert result is None
    assert svc.provider == "noop"


def test_mastermind_default_local_provider_materially_scores_risk():
    svc = MastermindService(provider="local")

    result = svc.advise(
        "BTCUSDT",
        {"ret_1": 0.001, "ret_3": 0.002, "realized_vol": 0.001, "spread_proxy": 0.0002, "depth_notional": 250000.0, "flow_imbalance": 0.2},
        "trend",
        forecast=SimpleNamespace(mu=0.0015, confidence=0.85),
        execution_quality=SimpleNamespace(fill_probability=0.85, adverse_selection_risk=0.1),
        event_intelligence_report=SimpleNamespace(overall_risk_score=0.1, recommended_action="continue"),
        market_integrity=SimpleNamespace(score=0.95, action="continue", reasons=[]),
    )

    assert result is not None
    assert result.provider == "local"
    assert result.decision in {"CONTINUE", "TRADE_SMALLER"}
    assert result.risk_level < 60.0
    assert result.raw["market_quality"] > 0.5


def test_mastermind_local_provider_vetoes_when_truth_or_integrity_is_weak():
    svc = MastermindService(provider="local")

    result = svc.advise(
        "BTCUSDT",
        {"ret_1": 0.001, "ret_3": 0.001, "realized_vol": 0.004, "spread_proxy": 0.003, "depth_notional": 500.0},
        "range",
        forecast=SimpleNamespace(mu=0.0001, confidence=0.55),
        execution_quality=SimpleNamespace(fill_probability=0.3, adverse_selection_risk=0.75),
        event_intelligence_report=SimpleNamespace(overall_risk_score=0.8, recommended_action="no_trade"),
        market_integrity=SimpleNamespace(score=0.2, action="flatten_only", reasons=["checksum_gap"]),
        truth_context={"snapshot": {"balance_truth_confidence": {"level": "unavailable"}}, "reconciliation_ok": False},
    )

    assert result is not None
    assert result.veto is True
    assert result.decision == "NO_TRADE"
    assert result.size_multiplier == 0.0
    assert result.reason in {"market_integrity_block", "truth_not_strong_enough", "hostile_future_breaks_thesis"}


def test_mastermind_groq_without_key_returns_unavailable(monkeypatch):
    monkeypatch.setenv("ADVISORY_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    svc = MastermindService()

    result = svc.advise("BTCUSDT", {"ret_1": 0.01}, "trend")

    assert result is not None
    assert result.signal == "unavailable"
    assert result.reason == "unavailable_or_missing_key"
    assert result.provider == "groq"


def test_mastermind_openai_without_key_returns_unavailable(monkeypatch):
    monkeypatch.setenv("ADVISORY_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    svc = MastermindService()

    result = svc.advise("BTCUSDT", {"ret_1": 0.01}, "range")

    assert result is not None
    assert result.signal == "unavailable"
    assert result.reason == "unavailable_or_missing_key"
    assert result.provider == "openai"


def test_mastermind_unknown_provider_returns_unavailable(monkeypatch):
    monkeypatch.setenv("ADVISORY_PROVIDER", "anthropic_xyz")
    svc = MastermindService()

    result = svc.advise("BTCUSDT", {}, "panic")

    assert result is not None
    assert result.signal == "unavailable"
    assert "unknown_provider" in result.reason
    assert result.provider == "anthropic_xyz"
