from autonomous_investment_robot.services.mastermind.service import MastermindService


def test_mastermind_noop_returns_none():
    svc = MastermindService()
    result = svc.advise("BTCUSDT", {"ret_1": 0.01}, "trend")
    assert result is None
    assert svc.provider == "noop"


def test_mastermind_groq_without_key_returns_unavailable(monkeypatch):
    monkeypatch.setenv("ADVISORY_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    svc = MastermindService()
    result = svc.advise("BTCUSDT", {"ret_1": 0.01}, "trend")
    assert result is not None
    assert result.signal == "unavailable"
    assert result.provider == "groq"
    assert "missing_api_key" in result.reason


def test_mastermind_openai_without_key_returns_unavailable(monkeypatch):
    monkeypatch.setenv("ADVISORY_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    svc = MastermindService()
    result = svc.advise("BTCUSDT", {"ret_1": 0.01}, "range")
    assert result is not None
    assert result.signal == "unavailable"
    assert result.provider == "openai"


def test_mastermind_unknown_provider_returns_unavailable(monkeypatch):
    monkeypatch.setenv("ADVISORY_PROVIDER", "anthropic_xyz")
    svc = MastermindService()
    result = svc.advise("BTCUSDT", {}, "panic")
    assert result is not None
    assert result.signal == "unavailable"
    assert "unknown_provider" in result.reason
