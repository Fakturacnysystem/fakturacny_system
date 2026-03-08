from __future__ import annotations

from dataclasses import asdict, dataclass
import json
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

    def preflight(self, harmony: ResolvedHarmonyConfig) -> MastermindSupervisorState:
        if float(harmony.sell_min_profit_bps) < 120.0:
            state = MastermindSupervisorState(
                ok=False,
                reason="sell_min_profit_bps_below_hard_floor",
                pause_buy=True,
                size_scale=0.05,
                max_orders_per_min_override=1,
                market_watch_max_calls_per_min_override=10,
                invariant_breach=True,
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
            )
            self._persist(state)
            return state
        pause = False
        size_scale = 1.0
        max_orders = None
        max_watch = None
        reason = "ok"
        if float(rate_limit_events) >= 3.0 or float(reject_rate) >= 0.5:
            pause = True
            size_scale = 0.4
            max_orders = max(1, int(base_max_orders_per_min * 0.5))
            max_watch = max(10, int(base_market_watch_budget * 0.5))
            reason = "rate_stress"
        elif float(insufficient_balance_events) >= 3.0:
            pause = True
            size_scale = 0.5
            max_orders = max(1, int(base_max_orders_per_min * 0.6))
            max_watch = max(10, int(base_market_watch_budget * 0.7))
            reason = "insufficient_balance_stress"
        elif float(no_intent_events) >= 10.0:
            size_scale = 0.8
            reason = "no_intent_soft"
        state = MastermindSupervisorState(
            ok=True,
            reason=reason,
            pause_buy=bool(pause),
            size_scale=float(size_scale),
            max_orders_per_min_override=max_orders,
            market_watch_max_calls_per_min_override=max_watch,
            invariant_breach=False,
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

