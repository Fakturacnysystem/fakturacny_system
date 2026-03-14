from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from autonomous_investment_robot.services.ops.harmony import ResolvedHarmonyConfig


@dataclass
class MastermindSupervisorState:
    ok: bool
    reason: str
    pause_buy: bool
    size_scale: float
    max_orders_per_min_override: int | None
    market_watch_max_calls_per_min_override: int | None
    invariant_breach: bool
    health: dict[str, Any] = field(default_factory=dict)
    guardrails: dict[str, Any] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    overrides: dict[str, Any] = field(default_factory=dict)


class MastermindSupervisor:
    """
    Deterministic control-plane supervisor.
    Never modifies hard sell profit-lock invariants.
    """

    def __init__(self, run_dir: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.status_path = self.run_dir / "mastermind_status.json"
        self.overrides_path = self.run_dir / "mastermind_overrides.json"

    def _hard_sell_floor_bps(self) -> float:
        raw = os.getenv(
            "AUTONOMOUS_SELL_HARD_MIN_PROFIT_BPS",
            os.getenv("AUTONOMOUS_SPOT_SELL_HARD_FLOOR_BPS", "30"),
        )
        try:
            out = float(raw)
        except Exception:
            return 30.0
        return max(0.0, out)

    def preflight(self, harmony: ResolvedHarmonyConfig) -> MastermindSupervisorState:
        hard_floor_bps = self._hard_sell_floor_bps()
        if float(harmony.sell_min_profit_bps) < hard_floor_bps:
            state = MastermindSupervisorState(
                ok=False,
                reason="sell_min_profit_bps_below_hard_floor",
                pause_buy=True,
                size_scale=0.05,
                max_orders_per_min_override=1,
                market_watch_max_calls_per_min_override=10,
                invariant_breach=True,
                health={"status": "FATAL", "component": "preflight"},
                guardrails={
                    "sell_min_profit_bps": float(harmony.sell_min_profit_bps),
                    "hard_floor_bps": float(hard_floor_bps),
                },
                conflicts=[f"sell_min_profit_bps_below_{int(hard_floor_bps)}"],
                overrides={"pause_buy": True, "size_scale": 0.05, "max_orders_per_min": 1},
            )
            self._persist(state)
            return state
        state = MastermindSupervisorState(
            ok=True,
            reason="ok",
            pause_buy=False,
            size_scale=1.0,
            max_orders_per_min_override=None,
            market_watch_max_calls_per_min_override=None,
            invariant_breach=False,
            health={"status": "OK", "component": "preflight"},
            guardrails={
                "sell_min_profit_bps": float(harmony.sell_min_profit_bps),
                "hard_floor_bps": float(hard_floor_bps),
            },
            conflicts=[],
            overrides={},
        )
        self._persist(state)
        return state

    def observe_runtime(
        self,
        *,
        reject_rate: float,
        rate_limit_events: float,
        insufficient_balance_events: float,
        no_intent_events: float,
        sell_breach_detected: bool,
        base_max_orders_per_min: int,
        base_market_watch_budget: int,
        guards_mode: str = "balanced",
    ) -> MastermindSupervisorState:
        if sell_breach_detected:
            state = MastermindSupervisorState(
                ok=False,
                reason="invariant_breach_sell_submitted_below_floor",
                pause_buy=True,
                size_scale=0.05,
                max_orders_per_min_override=1,
                market_watch_max_calls_per_min_override=10,
                invariant_breach=True,
                health={"status": "FATAL", "component": "runtime"},
                guardrails={"invariant_breach": True},
                conflicts=["profit_lock_invariant_breach"],
                overrides={"pause_buy": True, "size_scale": 0.05, "max_orders_per_min": 1},
            )
            self._persist(state)
            return state
        pause = False
        size_scale = 1.0
        max_orders = None
        max_watch = None
        reason = "ok"
        conflicts: list[str] = []
        rate_limit_events_f = float(rate_limit_events)
        reject_rate_f = float(reject_rate)
        insufficient_balance_events_f = float(insufficient_balance_events)
        no_intent_events_f = float(no_intent_events)
        guards_mode_norm = str(guards_mode or "balanced").strip().lower()
        fatal_only_mode = guards_mode_norm == "fatal_only"
        rate_limit_stress = rate_limit_events_f >= 5.0 and reject_rate_f >= 0.2
        reject_rate_stress = (
            reject_rate_f >= 0.8
            and (rate_limit_events_f >= 4.0 or insufficient_balance_events_f >= 3.0)
        )
        if rate_limit_stress or reject_rate_stress:
            pause = False if fatal_only_mode else True
            size_scale = 0.85 if fatal_only_mode else 0.4
            max_orders = None if fatal_only_mode else max(1, int(base_max_orders_per_min * 0.5))
            max_watch = None if fatal_only_mode else max(10, int(base_market_watch_budget * 0.5))
            reason = "rate_stress_warn" if fatal_only_mode else "rate_stress"
            conflicts.append("rate_limit_stress")
        elif insufficient_balance_events_f >= 3.0:
            pause = False if fatal_only_mode else True
            size_scale = 0.75 if fatal_only_mode else 0.5
            max_orders = None if fatal_only_mode else max(1, int(base_max_orders_per_min * 0.6))
            max_watch = None if fatal_only_mode else max(10, int(base_market_watch_budget * 0.7))
            reason = "insufficient_balance_warn" if fatal_only_mode else "insufficient_balance_stress"
            conflicts.append("insufficient_balance")
        elif no_intent_events_f >= 10.0:
            size_scale = 0.9 if fatal_only_mode else 0.8
            reason = "no_intent_soft"
            conflicts.append("no_intent")
        overrides: dict[str, Any] = {"pause_buy": bool(pause), "size_scale": float(size_scale)}
        if max_orders is not None:
            overrides["max_orders_per_min"] = int(max_orders)
        if max_watch is not None:
            overrides["market_watch_max_calls_per_min"] = int(max_watch)
        state = MastermindSupervisorState(
            ok=True,
            reason=reason,
            pause_buy=bool(pause),
            size_scale=float(size_scale),
            max_orders_per_min_override=max_orders,
            market_watch_max_calls_per_min_override=max_watch,
            invariant_breach=False,
            health={"status": "WARN" if conflicts else "OK", "component": "runtime"},
            guardrails={
                "reject_rate": reject_rate_f,
                "rate_limit_events": rate_limit_events_f,
                "insufficient_balance_events": insufficient_balance_events_f,
                "no_intent_events": no_intent_events_f,
            },
            conflicts=conflicts,
            overrides=overrides,
        )
        self._persist(state)
        return state

    def _persist(self, state: MastermindSupervisorState) -> None:
        payload = asdict(state)
        self.status_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        overrides: dict[str, Any] = {
            "pause_buy": bool(state.pause_buy),
            "size_scale": float(state.size_scale),
        }
        if state.max_orders_per_min_override is not None:
            overrides["max_orders_per_min"] = int(state.max_orders_per_min_override)
        if state.market_watch_max_calls_per_min_override is not None:
            overrides["market_watch_max_calls_per_min"] = int(state.market_watch_max_calls_per_min_override)
        self.overrides_path.write_text(json.dumps(overrides, sort_keys=True, indent=2), encoding="utf-8")
