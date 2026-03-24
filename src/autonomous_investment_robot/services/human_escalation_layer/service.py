from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from autonomous_investment_robot.core.contracts import HumanEscalationDecision


class HumanEscalationLayer:
    def __init__(self, run_dir: str | None = None, *, ack_ttl_minutes: int = 240) -> None:
        self.run_dir = None if run_dir is None else Path(run_dir)
        self.ack_ttl_minutes = max(1, int(ack_ttl_minutes))
        if self.run_dir is not None:
            self.run_dir.mkdir(parents=True, exist_ok=True)

    def _required_path(self) -> Path | None:
        if self.run_dir is None:
            return None
        return self.run_dir / "MANUAL_REVIEW_REQUIRED.json"

    def _ack_path(self) -> Path | None:
        if self.run_dir is None:
            return None
        return self.run_dir / "MANUAL_REVIEW_ACK.json"

    def _decision_key(self, *, symbol: str, action: str, severity: str, reasons: list[str], actions: list[str], distinct: list[str]) -> str:
        payload = {
            "symbol": symbol,
            "action": action,
            "severity": severity,
            "reasons": sorted(set(reasons)),
            "actions": list(actions),
            "distinct_actions": list(distinct),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]

    def _read_json(self, path: Path | None) -> dict[str, Any] | None:
        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def acknowledge(self, *, decision_key: str | None = None, reviewer: str = "operator", notes: str = "") -> dict[str, Any]:
        if self.run_dir is None:
            raise ValueError("acknowledgment_requires_run_dir")
        required = self._read_json(self._required_path())
        resolved_key = decision_key or (None if required is None else str(required.get("decision_key", "")))
        if not resolved_key:
            raise ValueError("manual_review_required_marker_missing")
        ack_payload = {
            "decision_key": resolved_key,
            "reviewer": reviewer,
            "notes": notes,
            "ack_ts": datetime.now(timezone.utc),
        }
        self._ack_path().write_text(json.dumps(ack_payload, sort_keys=True, default=str, indent=2), encoding="utf-8")
        return ack_payload

    def _acknowledgment(self, *, decision_key: str, symbol: str) -> dict[str, Any] | None:
        payload = self._read_json(self._ack_path())
        if payload is None:
            return None
        if str(payload.get("decision_key", "")) != decision_key:
            return None
        ack_ts_raw = payload.get("ack_ts")
        if isinstance(ack_ts_raw, str):
            try:
                ack_ts = datetime.fromisoformat(ack_ts_raw)
            except Exception:
                return None
        elif isinstance(ack_ts_raw, datetime):
            ack_ts = ack_ts_raw
        else:
            return None
        if ack_ts.tzinfo is None:
            ack_ts = ack_ts.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - ack_ts > timedelta(minutes=self.ack_ttl_minutes):
            return None
        scoped_symbol = str(payload.get("symbol", symbol or ""))
        if scoped_symbol and scoped_symbol not in {"*", symbol}:
            return None
        return payload

    def _persist(self, decision: HumanEscalationDecision) -> None:
        if self.run_dir is None:
            return
        payload = {
            "symbol": decision.symbol,
            "ts": decision.ts,
            "action": decision.action,
            "severity": decision.severity,
            "manual_review_required": decision.manual_review_required,
            "disagreement_score": decision.disagreement_score,
            "reasons": list(decision.reasons),
            "decision_key": decision.decision_key,
            "acknowledged": decision.acknowledged,
            "acknowledgment_source": decision.acknowledgment_source,
            "metadata": dict(decision.metadata),
        }
        required_path = self._required_path()
        if decision.action in {"manual_review", "flatten_only"} and required_path is not None:
            required_path.write_text(
                json.dumps(payload, sort_keys=True, default=str, indent=2),
                encoding="utf-8",
            )
        elif decision.acknowledged:
            ack_path = self._ack_path()
            if ack_path is not None and not ack_path.exists():
                ack_path.write_text(
                    json.dumps(
                        {
                            "decision_key": decision.decision_key,
                            "symbol": decision.symbol,
                            "reviewer": decision.acknowledgment_source or "operator",
                            "ack_ts": datetime.now(timezone.utc),
                            "notes": "implicit_ack_state_refresh",
                        },
                        sort_keys=True,
                        default=str,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            required = self._read_json(required_path)
            if required is not None and str(required.get("decision_key", "")) == decision.decision_key:
                required_path.unlink(missing_ok=True)

    def evaluate(
        self,
        *,
        symbol: str,
        ts: datetime,
        market_integrity: Any | None = None,
        quantum_state: Any | None = None,
        edge_immunity_decision: Any | None = None,
        event_intelligence: Any | None = None,
        synthetic_affect: Any | None = None,
        capital_sovereignty: Any | None = None,
        execution_simulation: Any | None = None,
    ) -> HumanEscalationDecision:
        actions: list[str] = []
        reasons: list[str] = []
        disagreement_score = 0.0
        if market_integrity is not None:
            actions.append(str(getattr(market_integrity, "action", "continue")))
            if str(getattr(market_integrity, "action", "continue")) in {"flatten_only", "halt"}:
                reasons.append("market_integrity_severe")
        if quantum_state is not None:
            collapse = getattr(quantum_state, "collapse_decision", None)
            if collapse is not None:
                actions.append(str(getattr(collapse, "recommended_action", "continue")))
                if float(getattr(collapse, "uncertainty", 0.0) or 0.0) >= 0.8:
                    reasons.append("quantum_uncertainty_extreme")
        if edge_immunity_decision is not None:
            actions.append(str(getattr(edge_immunity_decision, "action", "continue")))
        if event_intelligence is not None:
            actions.append(str(getattr(event_intelligence, "recommended_action", "continue")))
        if synthetic_affect is not None:
            actions.append(str(getattr(synthetic_affect, "recommended_action", "continue")))
            if max(float(getattr(synthetic_affect, "stress", 0.0) or 0.0), float(getattr(synthetic_affect, "fear", 0.0) or 0.0)) >= 0.8:
                reasons.append("synthetic_stress_extreme")
        if capital_sovereignty is not None:
            actions.append(str(getattr(capital_sovereignty, "action", "continue")))
        if execution_simulation is not None:
            actions.append(str(getattr(execution_simulation, "recommended_action", "continue")))
            if float(getattr(execution_simulation, "stressed_fill_probability", 1.0) or 1.0) <= 0.2:
                reasons.append("execution_simulation_breaks_trade")

        distinct = {action for action in actions if action and action != "continue"}
        if actions:
            disagreement_score = min(1.0, max(0.0, (len(distinct) - 1) / max(len(actions), 1) + 0.15 * len(reasons)))
        action = "continue"
        severity = "info"
        manual_review_required = False
        distinct_actions = sorted(distinct)
        if "market_integrity_severe" in reasons:
            action = "flatten_only"
            severity = "critical"
            manual_review_required = True
        elif disagreement_score >= 0.65 or len(reasons) >= 2:
            action = "manual_review"
            severity = "high"
            manual_review_required = True
        elif disagreement_score >= 0.4:
            action = "manual_review"
            severity = "medium"
            manual_review_required = True
        decision_key = self._decision_key(
            symbol=symbol,
            action=action,
            severity=severity,
            reasons=sorted(set(reasons)),
            actions=actions,
            distinct=distinct_actions,
        )
        ack_payload = None
        acknowledged = False
        acknowledgment_source = ""
        if action == "manual_review":
            ack_payload = self._acknowledgment(decision_key=decision_key, symbol=symbol)
            if ack_payload is not None:
                action = "continue_acknowledged"
                severity = "info"
                manual_review_required = False
                acknowledged = True
                acknowledgment_source = str(ack_payload.get("reviewer", "operator"))
        decision = HumanEscalationDecision(
            symbol=symbol,
            ts=ts,
            action=action,
            severity=severity,
            manual_review_required=manual_review_required,
            disagreement_score=disagreement_score,
            reasons=sorted(set(reasons)),
            decision_key=decision_key,
            acknowledged=acknowledged,
            acknowledgment_source=acknowledgment_source,
            metadata={
                "actions": actions,
                "distinct_actions": distinct_actions,
                "acknowledgment": ack_payload,
            },
        )
        self._persist(decision)
        return decision
