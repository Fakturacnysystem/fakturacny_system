from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Mapping


OPENAI_BASE_URL = "https://api.openai.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    model: str
    model_fallback: str
    base_url: str
    api_key_env: str
    enabled: bool
    timeout_s: float
    max_retries: int
    healthcheck_remote: bool


def _classify_provider_error(err_text: str) -> str:
    txt = str(err_text or "").lower()
    if not txt:
        return "unknown_error"
    if "invalid api key" in txt or "incorrect api key" in txt or "invalid_key" in txt:
        return "invalid_credentials"
    if "401" in txt or "unauthorized" in txt or "authentication" in txt:
        return "invalid_credentials"
    if "403" in txt or "permission" in txt:
        return "invalid_permissions"
    if "429" in txt or "rate limit" in txt or "temporary lockout" in txt:
        return "rate_limit"
    if "timeout" in txt:
        return "timeout"
    if "dns" in txt or "connection" in txt or "network" in txt:
        return "network_unreachable"
    return "unknown_error"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, str(default)) or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def resolve_provider_config(
    *,
    env: Mapping[str, str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    model_fallback: str | None = None,
    base_url: str | None = None,
    enabled: bool | None = None,
    timeout_s: float | None = None,
    max_retries: int | None = None,
    healthcheck_remote: bool | None = None,
) -> LLMProviderConfig:
    source = dict(os.environ if env is None else env)
    key_openai = str(source.get("OPENAI_API_KEY", "") or "").strip()
    key_groq = str(source.get("GROQ_API_KEY", "") or "").strip()
    env_provider = str(source.get("LLM_PROVIDER", "") or "").strip().lower()
    chosen_provider = str(provider or env_provider or "auto").strip().lower()

    if chosen_provider in {"", "auto"}:
        if key_groq and not key_openai:
            chosen_provider = "groq"
        elif key_openai:
            chosen_provider = "openai"
        elif key_groq:
            chosen_provider = "groq"
        else:
            chosen_provider = "groq"

    if chosen_provider not in {"openai", "groq"}:
        chosen_provider = "groq"

    if chosen_provider == "groq":
        api_env = "GROQ_API_KEY"
        default_model = DEFAULT_GROQ_MODEL
        default_url = GROQ_BASE_URL
        key = key_groq
    else:
        api_env = "OPENAI_API_KEY"
        default_model = DEFAULT_OPENAI_MODEL
        default_url = OPENAI_BASE_URL
        key = key_openai

    cfg_enabled = bool(enabled) if enabled is not None else _env_bool("LLM_ENABLED", True)
    cfg_timeout = (
        max(1.0, float(timeout_s))
        if timeout_s is not None
        else max(1.0, float(source.get("LLM_TIMEOUT_S", "12.0") or "12.0"))
    )
    cfg_retries = (
        max(0, int(max_retries))
        if max_retries is not None
        else max(0, int(float(source.get("LLM_MAX_RETRIES", "1") or "1")))
    )
    cfg_healthcheck_remote = (
        bool(healthcheck_remote)
        if healthcheck_remote is not None
        else _env_bool("LLM_HEALTHCHECK_REMOTE", False)
    )

    cfg_model = str(
        model
        or source.get("LLM_MODEL_PRIMARY")
        or source.get("LLM_MODEL")
        or source.get("OPENAI_MODEL")
        or default_model
    ).strip() or default_model
    cfg_model_fallback = str(
        model_fallback
        or source.get("LLM_MODEL_FALLBACK")
        or source.get("OPENAI_MODEL_FALLBACK")
        or ""
    ).strip()
    if cfg_model_fallback and cfg_model_fallback == cfg_model:
        cfg_model_fallback = ""
    cfg_base_url = str(base_url or source.get("LLM_BASE_URL") or default_url).strip() or default_url

    return LLMProviderConfig(
        provider=chosen_provider,
        model=cfg_model,
        model_fallback=cfg_model_fallback,
        base_url=cfg_base_url,
        api_key_env=api_env,
        enabled=bool(cfg_enabled and bool(key)),
        timeout_s=cfg_timeout,
        max_retries=cfg_retries,
        healthcheck_remote=cfg_healthcheck_remote,
    )


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", "") or ""
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    output_items = getattr(response, "output", None)
    if not isinstance(output_items, list):
        return ""
    pieces: list[str] = []
    for item in output_items:
        contents = getattr(item, "content", None)
        if not isinstance(contents, list):
            continue
        for content in contents:
            text = getattr(content, "text", None)
            if isinstance(text, str) and text:
                pieces.append(text)
    return "".join(pieces)


class LLMProviderClient:
    def __init__(self, config: LLMProviderConfig, *, env: Mapping[str, str] | None = None) -> None:
        self.config = config
        self._env = dict(os.environ if env is None else env)
        self._api_key = str(self._env.get(self.config.api_key_env, "") or "").strip()
        self._last_model_used = str(self.config.model)

    @property
    def key_present(self) -> bool:
        return bool(self._api_key)

    @property
    def last_model_used(self) -> str:
        return str(self._last_model_used or self.config.model)

    def create_client(self) -> Any:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("dependency_missing:openai") from exc
        return OpenAI(
            api_key=self._api_key,
            base_url=self.config.base_url,
            max_retries=int(self.config.max_retries),
            timeout=float(self.config.timeout_s),
        )

    def health_check(self, *, remote: bool | None = None) -> dict[str, Any]:
        remote_check = self.config.healthcheck_remote if remote is None else bool(remote)
        payload = {
            "provider": self.config.provider,
            "enabled": bool(self.config.enabled),
            "api_key_env": self.config.api_key_env,
            "key_present": bool(self.key_present),
            "model": self.config.model,
            "model_fallback": self.config.model_fallback,
            "base_url": self.config.base_url,
            "remote_checked": bool(remote_check),
            "ok": False,
            "classification": "",
            "reason": "",
        }
        if not self.config.enabled:
            payload["classification"] = "disabled"
            payload["reason"] = "llm_disabled_or_missing_key"
            return payload
        if not self.key_present:
            payload["classification"] = "missing_credentials"
            payload["reason"] = f"{self.config.api_key_env}_missing"
            return payload
        try:
            client = self.create_client()
        except Exception as exc:
            payload["classification"] = _classify_provider_error(str(exc))
            payload["reason"] = str(exc)
            return payload
        if not remote_check:
            payload["classification"] = "ok_local"
            payload["ok"] = True
            return payload
        try:
            models = client.models.list()
            count = len(getattr(models, "data", []) or [])
            payload["classification"] = "ok_remote"
            payload["ok"] = True
            payload["models_count"] = int(count)
            return payload
        except Exception as exc:
            payload["classification"] = _classify_provider_error(str(exc))
            payload["reason"] = str(exc)
            return payload

    def create_structured_json(
        self,
        *,
        instructions: str,
        user_payload: Mapping[str, Any],
        schema_name: str,
        schema: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self.config.enabled or not self.key_present:
            raise RuntimeError("llm_unavailable")
        client = self.create_client()
        models = [self.config.model]
        if self.config.model_fallback:
            models.append(self.config.model_fallback)
        last_exc: Exception | None = None
        for idx, model_name in enumerate(models):
            try:
                response = client.responses.create(
                    model=model_name,
                    instructions=str(instructions),
                    input=[
                        {
                            "role": "user",
                            "content": json.dumps(dict(user_payload), ensure_ascii=False),
                        }
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": str(schema_name),
                            "schema": dict(schema),
                            "strict": True,
                        }
                    },
                )
                text = _extract_response_text(response)
                if not text.strip():
                    raise RuntimeError("llm_empty_output")
                parsed = json.loads(text)
                if not isinstance(parsed, dict):
                    raise RuntimeError("llm_invalid_json_root")
                self._last_model_used = str(model_name)
                return parsed
            except Exception as exc:
                last_exc = exc
                if idx + 1 >= len(models):
                    break
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("llm_no_model_available")
