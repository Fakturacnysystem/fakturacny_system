from __future__ import annotations

import json
import logging
import os
from typing import Any

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency guard
    OpenAI = None  # type: ignore[assignment]

logger = logging.getLogger("Oracle-Engine")


class OracleEngine:
    def __init__(self, api_key: str | None = None, *, base_url: str | None = None, model: str = "meta/llama-3.1-405b-instruct") -> None:
        self.api_key = (api_key or os.getenv("NVIDIA_API_KEY", "")).strip()
        self.base_url = (base_url or os.getenv("NVIDIA_API_BASE_URL", "https://integrate.api.nvidia.com/v1")).strip()
        self.model = model
        self.enabled = bool(self.api_key) and OpenAI is not None
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key) if self.enabled and OpenAI is not None else None

    def predict_move(self, ob_imbalance: float, sentiment: float, correlations: Any) -> dict[str, Any]:
        if not self.enabled or self.client is None:
            return {
                "direction": "STAGNATE",
                "confidence": 0,
                "enabled": False,
                "reason": "oracle_disabled_missing_api_key" if not self.api_key else "oracle_disabled_missing_openai_dependency",
            }

        prompt = (
            f"Synthesize market future: OB_Imbalance={ob_imbalance}, "
            f"Sentiment={sentiment}, Correlations={correlations}. "
            "Return strictly JSON: {\"direction\": \"UP/DOWN/STAGNATE\", \"confidence\": 0-100}"
        )
        try:
            res = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": prompt}],
                response_format={"type": "json_object"},
            )
            payload = json.loads(res.choices[0].message.content)
            payload.setdefault("enabled", True)
            return payload
        except Exception as exc:
            logger.error("Oracle Error: %s", exc)
            return {
                "direction": "STAGNATE",
                "confidence": 0,
                "enabled": True,
                "reason": "oracle_request_failed",
                "error": str(exc),
            }
