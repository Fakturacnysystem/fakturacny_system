from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MastermindAdvisory:
    decision: str
    confidence: float
    reason: str
    risk_level: float = 100.0
    veto: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


class MastermindService:
    def __init__(self) -> None:
        self.provider = os.getenv("ADVISORY_PROVIDER", "noop").strip().lower() or "noop"
        self.groq_api_key = os.getenv("GROQ_API_KEY", "").strip()

    def advise(self, symbol: str, features: dict[str, Any], regime: str) -> MastermindAdvisory | None:
        if self.provider == "noop":
            return None

        if self.provider == "groq":
            if not self.groq_api_key:
                return MastermindAdvisory(
                    decision="HOLD",
                    confidence=0.0,
                    reason="provider_unavailable",
                    risk_level=100.0,
                    veto=False,
                    raw={
                        "provider": "groq",
                        "symbol": symbol,
                        "regime": regime,
                        "features": features,
                        "error": "missing_groq_api_key",
                    },
                )

            return MastermindAdvisory(
                decision="HOLD",
                confidence=0.0,
                reason="provider_not_implemented",
                risk_level=100.0,
                veto=False,
                raw={
                    "provider": "groq",
                    "symbol": symbol,
                    "regime": regime,
                    "features": features,
                },
            )

        return MastermindAdvisory(
            decision="HOLD",
            confidence=0.0,
            reason="unknown_provider",
            risk_level=100.0,
            veto=False,
            raw={
                "provider": self.provider,
                "symbol": symbol,
                "regime": regime,
                "features": features,
            },
        )
