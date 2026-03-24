from types import SimpleNamespace

from autonomous_investment_robot.services.mastermind.oracle_service import OracleEngine


def test_oracle_engine_is_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    engine = OracleEngine()
    result = engine.predict_move(0.1, 0.2, {"btc": 0.8})

    assert engine.enabled is False
    assert result["direction"] == "STAGNATE"
    assert result["confidence"] == 0
    assert result["reason"] == "oracle_disabled_missing_api_key"


def test_oracle_engine_uses_injected_client(monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):  # noqa: ANN003
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"direction":"UP","confidence":77}'))])

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr("autonomous_investment_robot.services.mastermind.oracle_service.OpenAI", lambda **kwargs: FakeClient())

    engine = OracleEngine(api_key="test-key")
    result = engine.predict_move(0.1, 0.2, {"btc": 0.8})

    assert engine.enabled is True
    assert result["direction"] == "UP"
    assert result["confidence"] == 77
    assert result["enabled"] is True
