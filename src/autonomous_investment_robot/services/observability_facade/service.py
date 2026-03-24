from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from autonomous_investment_robot.services.observability_service.service import ObservabilityService


class ObservabilityFacade:
    def __init__(self, base: ObservabilityService) -> None:
        self.base = base
        self.run_dir = base.run_dir
        self.ops = base.ops

    def _serialize(self, payload: Any) -> dict[str, Any] | list[Any] | str | int | float | bool | None:
        if is_dataclass(payload):
            payload = asdict(payload)
        return json.loads(json.dumps(payload, sort_keys=True, default=str))

    def _route_index(self, *, category: str, channel: str, payload: Any) -> None:
        serializable = self._serialize(payload)
        if isinstance(serializable, dict):
            symbol = str(serializable.get("symbol", ""))
            ts = serializable.get("ts")
        else:
            symbol = ""
            ts = None
        out = Path(self.run_dir) / "observability_route_index.jsonl"
        with out.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "category": category,
                        "channel": channel,
                        "symbol": symbol,
                        "ts": ts,
                    },
                    sort_keys=True,
                    default=str,
                )
                + "\n"
            )

    def journal(self, channel: str, payload: Any) -> None:
        self.base.journal(channel, payload)
        self._route_index(category="journal", channel=channel, payload=payload)

    def route_spre(self, payload: Any) -> None:
        self.base.journal("spre_journal", payload)
        self._route_index(category="spre", channel="spre_journal", payload=payload)

    def route_shadow(self, payload: Any) -> None:
        self.base.journal("shadow_rival_journal", payload)
        self._route_index(category="shadow", channel="shadow_rival_journal", payload=payload)

    def route_mastermind(self, payload: Any) -> None:
        self.base.journal("mastermind_journal", payload)
        self._route_index(category="mastermind", channel="mastermind_journal", payload=payload)

    def route_decision_doctrine(self, payload: Any) -> None:
        self.base.journal("decision_doctrine_journal", payload)
        self._route_index(category="decision_doctrine", channel="decision_doctrine_journal", payload=payload)

    def route_truth_evidence(self, channel: str, payload: Any) -> None:
        self.base.journal(channel, payload)
        self._route_index(category="truth_evidence", channel=channel, payload=payload)

    def route_lifecycle(self, payload: Any) -> None:
        self.base.journal("lifecycle_evidence_journal", payload)
        self._route_index(category="lifecycle", channel="lifecycle_evidence_journal", payload=payload)

    def route_execution_simulation(self, payload: Any) -> None:
        self.base.journal("execution_simulation_journal", payload)
        self._route_index(category="execution_simulation", channel="execution_simulation_journal", payload=payload)

    def route_escalation(self, payload: Any) -> None:
        self.base.journal("human_escalation_journal", payload)
        self._route_index(category="escalation", channel="human_escalation_journal", payload=payload)

    def route_counterfactual(self, payload: Any) -> None:
        self.base.journal("counterfactual_review", payload)
        self._route_index(category="counterfactual", channel="counterfactual_review", payload=payload)

    def route_analog_lookup(self, payload: Any) -> None:
        self.base.journal("analog_trade_lookup", payload)
        self._route_index(category="analog_lookup", channel="analog_trade_lookup", payload=payload)

    def route_calibration(self, payload: Any) -> None:
        self.base.journal("calibration_profile", payload)
        self._route_index(category="calibration", channel="calibration_profile", payload=payload)
