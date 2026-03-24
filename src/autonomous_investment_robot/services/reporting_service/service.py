from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from typing import Any


class ReportingCoordinator:
    def __init__(self, *, observability: Any) -> None:
        self.observability = observability

    def _serialize(self, payload: Any) -> Any:
        if is_dataclass(payload):
            return asdict(payload)
        return payload

    def build_operator_summary(self, *, channel: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.observability.journal(channel, payload)
        return payload

    def report_profitability(
        self,
        *,
        symbol: str,
        profitability: Any,
        reserve_state: Any | None = None,
        inventory_state: Any | None = None,
    ) -> dict[str, Any]:
        profitability_payload = self._serialize(profitability)
        capital_release = profitability_payload.get("capital_release", {}) if isinstance(profitability_payload, dict) else {}
        round_trip = profitability_payload.get("round_trip", {}) if isinstance(profitability_payload, dict) else {}
        payload = {
            "symbol": symbol,
            "profitability": profitability_payload,
            "reserve_state": None if reserve_state is None else self._serialize(reserve_state),
            "inventory_state": None if inventory_state is None else self._serialize(inventory_state),
            "quote_balance_deadlock": bool(capital_release.get("allowed", False) and "reserve" in str(capital_release.get("reason", ""))),
            "inventory_stagnation": bool(capital_release.get("allowed", False) and "stale" in json.dumps(capital_release, sort_keys=True, default=str)),
            "profit_lock_candidate": str(capital_release.get("reason", "")) == "profit_lock_partial_exit",
        }
        return self.build_operator_summary(channel="operator_summary", payload=payload)

    def report_capital_strategy(
        self,
        *,
        symbol: str,
        event_intelligence: Any | None = None,
        synthetic_affect: Any | None = None,
        capital_sovereignty: Any | None = None,
        position_morph: Any | None = None,
        adaptive_exit: Any | None = None,
    ) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "event_intelligence": None if event_intelligence is None else self._serialize(event_intelligence),
            "synthetic_affect": None if synthetic_affect is None else self._serialize(synthetic_affect),
            "capital_sovereignty": None if capital_sovereignty is None else self._serialize(capital_sovereignty),
            "position_morph": None if position_morph is None else self._serialize(position_morph),
            "adaptive_exit": None if adaptive_exit is None else self._serialize(adaptive_exit),
        }
        return self.build_operator_summary(channel="capital_strategy_summary", payload=payload)

    def report_decision_doctrine(
        self,
        *,
        symbol: str,
        decision_doctrine: Any,
        truth_context: Any | None = None,
        market_integrity: Any | None = None,
        provider_capability: Any | None = None,
    ) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "decision_doctrine": self._serialize(decision_doctrine),
            "truth_context": None if truth_context is None else self._serialize(truth_context),
            "market_integrity": None if market_integrity is None else self._serialize(market_integrity),
            "provider_capability": None if provider_capability is None else self._serialize(provider_capability),
        }
        return self.build_operator_summary(channel="decision_doctrine_summary", payload=payload)

    def report_mastermind(self, *, symbol: str, mastermind: Any) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "mastermind": None if mastermind is None else self._serialize(mastermind),
        }
        return self.build_operator_summary(channel="mastermind_summary", payload=payload)
