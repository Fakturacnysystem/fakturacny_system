from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import os
import time
from typing import Any

from autonomous_investment_robot.services.policy.service import OrderIntent


@dataclass
class MastermindConfig:
    enabled: bool = True
    max_entry_orders_per_min: int = 6
    allow_entry_side_flip: bool = False

    @classmethod
    def from_env(cls) -> "MastermindConfig":
        raw_enabled = os.getenv("AUTONOMOUS_MASTERMIND_ENABLED")
        enabled = True if raw_enabled is None else str(raw_enabled).strip().lower() in {"1", "true", "yes", "on"}
        raw_allow_entry_side_flip = os.getenv("AUTONOMOUS_MASTERMIND_ALLOW_ENTRY_SIDE_FLIP")
        allow_entry_side_flip = (
            False
            if raw_allow_entry_side_flip is None
            else str(raw_allow_entry_side_flip).strip().lower() in {"1", "true", "yes", "on"}
        )
        try:
            max_orders = int(float(os.getenv("AUTONOMOUS_MASTERMIND_MAX_ENTRY_ORDERS_PER_MIN", "6") or "6"))
        except Exception:
            max_orders = 6
        return cls(
            enabled=enabled,
            max_entry_orders_per_min=max(1, max_orders),
            allow_entry_side_flip=allow_entry_side_flip,
        )


@dataclass
class MastermindDecision:
    allowed: bool
    mode: str
    reason: str
    intent: OrderIntent | None
    score: float
    selected_strategy: str


class MastermindPolicy:
    """Single decision layer that scores strategy signals and enforces entry budget/modes."""

    def __init__(self, config: MastermindConfig | None = None) -> None:
        self.config = config or MastermindConfig.from_env()
        self._entry_submission_ts: deque[float] = deque(maxlen=1024)

    def mode(self, *, exits_only: bool, rate_limit_storm: bool, ws_healthy: bool) -> str:
        if exits_only or (not ws_healthy):
            return "exits_only"
        if rate_limit_storm:
            return "normal"
        profile = str(os.getenv("AUTONOMOUS_PROFILE", "") or "").strip().lower()
        if profile in {"normal", "balanced", "conservative"}:
            return "normal"
        return "aggressive_hf"

    def _trim(self, now_ts: float) -> None:
        while self._entry_submission_ts and (now_ts - self._entry_submission_ts[0]) > 60.0:
            self._entry_submission_ts.popleft()

    def _can_open_entry(self, now_ts: float) -> bool:
        self._trim(now_ts)
        return len(self._entry_submission_ts) < int(self.config.max_entry_orders_per_min)

    def note_entry_submission(self, *, now_ts: float | None = None) -> None:
        now = time.time() if now_ts is None else float(now_ts)
        self._entry_submission_ts.append(now)

    @staticmethod
    def score_candidate(
        *,
        edge_bps: float,
        confidence: float,
        costs_bps: float,
        risk_penalty: float,
        churn_penalty: float,
        stuck_penalty: float,
    ) -> float:
        return (
            float(edge_bps) * float(confidence)
            - float(costs_bps)
            - float(risk_penalty)
            - float(churn_penalty)
            - float(stuck_penalty)
        )

    def choose(
        self,
        *,
        base_intent: OrderIntent,
        now_ts: float,
        mode: str,
        risk_penalty: float = 0.0,
        churn_penalty: float = 0.0,
        stuck_penalty: float = 0.0,
    ) -> MastermindDecision:
        if not self.config.enabled:
            return MastermindDecision(
                allowed=True,
                mode=str(mode),
                reason="mastermind_disabled",
                intent=base_intent,
                score=0.0,
                selected_strategy="",
            )

        side = str(base_intent.side).lower()
        is_entry = side == "buy"
        if str(mode) == "exits_only" and is_entry:
            return MastermindDecision(
                allowed=False,
                mode="exits_only",
                reason="mastermind_exits_only",
                intent=None,
                score=0.0,
                selected_strategy="",
            )

        if is_entry and not self._can_open_entry(now_ts):
            return MastermindDecision(
                allowed=False,
                mode=str(mode),
                reason="mastermind_entry_budget",
                intent=None,
                score=0.0,
                selected_strategy="",
            )

        why = base_intent.why if isinstance(base_intent.why, dict) else {}
        components = why.get("components", []) if isinstance(why, dict) else []
        mission_bridge = why.get("mission_bridge", {}) if isinstance(why, dict) else {}
        if not isinstance(mission_bridge, dict):
            mission_bridge = {}
        if not isinstance(components, list) or not components:
            return MastermindDecision(
                allowed=True,
                mode=str(mode),
                reason="mastermind_no_components",
                intent=base_intent,
                score=0.0,
                selected_strategy="",
            )

        best_score = float("-inf")
        best_component: dict[str, Any] | None = None
        for comp in components:
            if not isinstance(comp, dict):
                continue
            c_edge = float(comp.get("final_edge_bps", comp.get("edge_bps", 0.0)) or 0.0)
            # Backward-compatible default: legacy components often omit confidence.
            c_conf = float(comp.get("confidence", 1.0) or 1.0)
            c_cost = float(comp.get("cost_total_bps", 0.0) or 0.0)
            sc = self.score_candidate(
                edge_bps=c_edge,
                confidence=c_conf,
                costs_bps=c_cost,
                risk_penalty=risk_penalty,
                churn_penalty=churn_penalty,
                stuck_penalty=stuck_penalty,
            )
            if sc > best_score:
                best_score = sc
                best_component = comp

        if best_component is None:
            return MastermindDecision(
                allowed=True,
                mode=str(mode),
                reason="mastermind_no_best_component",
                intent=base_intent,
                score=0.0,
                selected_strategy="",
            )

        selected_strategy = str(best_component.get("strategy", "") or "")
        signal_side = str(best_component.get("signal_side", side) or side).lower()
        signal_notional = abs(float(best_component.get("signal_notional", base_intent.target_notional) or base_intent.target_notional))
        if signal_notional <= 0.0:
            signal_notional = float(base_intent.target_notional)

        # Enforce positive score only for new entries; exits still pass through.
        if is_entry and best_score <= 0.0:
            return MastermindDecision(
                allowed=False,
                mode=str(mode),
                reason="mastermind_score_below_zero",
                intent=None,
                score=float(best_score),
                selected_strategy=selected_strategy,
            )

        side_out = signal_side if signal_side in {"buy", "sell"} else side
        notional_out = float(signal_notional)
        side_flip_blocked = False
        # Keep entry intents tradeable in SPOT mode: by default, do not let
        # a buy-intent get flipped into sell by strategy-side hints.
        if is_entry and side_out == "sell" and not bool(self.config.allow_entry_side_flip):
            side_out = "buy"
            notional_out = float(base_intent.target_notional)
            side_flip_blocked = True
        intent = OrderIntent(
            symbol=base_intent.symbol,
            side=side_out,
            target_notional=notional_out,
            why={
                **(base_intent.why if isinstance(base_intent.why, dict) else {}),
                "mastermind": {
                    "mode": str(mode),
                    "selected_strategy": selected_strategy,
                    "score": float(best_score),
                    "entry_side_flip_blocked": bool(side_flip_blocked),
                    "entry_side_flip_original_signal_side": str(signal_side),
                    "mission_advisory": {
                        "mission": str(mission_bridge.get("mission", "") or ""),
                        "reason_codes": list(mission_bridge.get("reason_codes", []))
                        if isinstance(mission_bridge.get("reason_codes", []), list)
                        else [],
                        "no_trade_preferred": bool(mission_bridge.get("no_trade_preferred", False)),
                        "allow_new_risk": bool(mission_bridge.get("allow_new_risk", True)),
                    },
                },
            },
        )
        return MastermindDecision(
            allowed=True,
            mode=str(mode),
            reason="mastermind_selected",
            intent=intent,
            score=float(best_score),
            selected_strategy=selected_strategy,
        )
