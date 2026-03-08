from __future__ import annotations

from autonomous_investment_robot.services.llm.provider import (
    LLMProviderClient,
    resolve_provider_config,
)


def test_resolve_provider_auto_prefers_groq_when_openai_missing() -> None:
    cfg = resolve_provider_config(
        env={
            "GROQ_API_KEY": "gsk-test",
            "OPENAI_API_KEY": "",
        }
    )
    assert cfg.provider == "groq"
    assert cfg.api_key_env == "GROQ_API_KEY"
    assert cfg.enabled is True


def test_resolve_provider_openai_explicit() -> None:
    cfg = resolve_provider_config(
        env={
            "GROQ_API_KEY": "gsk-test",
            "OPENAI_API_KEY": "sk-test",
        },
        provider="openai",
    )
    assert cfg.provider == "openai"
    assert cfg.api_key_env == "OPENAI_API_KEY"
    assert cfg.enabled is True


def test_health_check_reports_missing_credentials() -> None:
    cfg = resolve_provider_config(
        env={
            "GROQ_API_KEY": "",
            "OPENAI_API_KEY": "",
        },
        provider="groq",
    )
    client = LLMProviderClient(cfg, env={"GROQ_API_KEY": ""})
    out = client.health_check(remote=False)
    assert out["ok"] is False
    assert out["classification"] in {"disabled", "missing_credentials"}


def test_health_check_remote_classifies_invalid_key(monkeypatch) -> None:
    cfg = resolve_provider_config(
        env={"GROQ_API_KEY": "gsk-test"},
        provider="groq",
        healthcheck_remote=True,
    )
    client = LLMProviderClient(cfg, env={"GROQ_API_KEY": "gsk-test"})

    class _FakeModels:
        @staticmethod
        def list():
            raise RuntimeError("Invalid API Key")

    class _FakeOpenAIClient:
        models = _FakeModels()

    monkeypatch.setattr(client, "create_client", lambda: _FakeOpenAIClient())
    out = client.health_check(remote=True)
    assert out["ok"] is False
    assert out["classification"] == "invalid_credentials"


def test_resolve_provider_model_primary_and_fallback() -> None:
    cfg = resolve_provider_config(
        env={
            "GROQ_API_KEY": "gsk-test",
            "LLM_MODEL_PRIMARY": "openai/gpt-oss-120b",
            "LLM_MODEL_FALLBACK": "openai/gpt-oss-20b",
        },
        provider="groq",
    )
    assert cfg.model == "openai/gpt-oss-120b"
    assert cfg.model_fallback == "openai/gpt-oss-20b"


def test_structured_json_falls_back_to_secondary_model(monkeypatch) -> None:
    cfg = resolve_provider_config(
        env={"GROQ_API_KEY": "gsk-test"},
        provider="groq",
        model="primary-model",
        model_fallback="fallback-model",
    )
    client = LLMProviderClient(cfg, env={"GROQ_API_KEY": "gsk-test"})
    calls: list[str] = []

    class _FakeResp:
        output_text = "{\"suggestions\":[]}"

    class _FakeResponses:
        @staticmethod
        def create(*, model, **kwargs):  # noqa: ANN001
            _ = kwargs
            calls.append(str(model))
            if model == "primary-model":
                raise RuntimeError("temporary failure")
            return _FakeResp()

    class _FakeClient:
        responses = _FakeResponses()

    monkeypatch.setattr(client, "create_client", lambda: _FakeClient())
    payload = client.create_structured_json(
        instructions="x",
        user_payload={"a": 1},
        schema_name="schema",
        schema={"type": "object", "properties": {"suggestions": {"type": "array"}}, "required": ["suggestions"], "additionalProperties": False},
    )
    assert payload == {"suggestions": []}
    assert calls == ["primary-model", "fallback-model"]
    assert client.last_model_used == "fallback-model"
