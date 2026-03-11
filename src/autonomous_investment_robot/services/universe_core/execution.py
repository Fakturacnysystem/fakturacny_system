from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .mission import MissionDecision
from .parliament import StrategyProposal
from .state import WorldStateSnapshot


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass(frozen=True)
class ExecutionPlan:
    instrument: str
    side: str
    actionable: bool
    target_notional_quote: float
    target_size: float
    max_slippage_bps: float
    order_type: str
    maker_taker: str
    urgency_tier: str
    repricing_logic: str
    timeout_s: float
    exit_doctrine: str
    expected_fill_quality: float
    retry_policy: str
    cancel_replace_budget: int
    queue_quality: float
    meta: dict[str, Any] = field(default_factory=dict)

    def scaled(self, size_scale: float) -> "ExecutionPlan":
        scale = max(0.0, float(size_scale))
        return replace(
            self,
            target_notional_quote=float(self.target_notional_quote) * scale,
            target_size=float(self.target_size) * scale,
            meta={**self.meta, "size_scale": scale},
        )

    def as_non_actionable(self, reason: str) -> "ExecutionPlan":
        return replace(
            self,
            actionable=False,
            target_notional_quote=0.0,
            target_size=0.0,
            order_type="none",
            maker_taker="none",
            urgency_tier="none",
            meta={**self.meta, "blocked_reason": str(reason)},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument,
            "side": self.side,
            "actionable": self.actionable,
            "target_notional_quote": self.target_notional_quote,
            "target_size": self.target_size,
            "max_slippage_bps": self.max_slippage_bps,
            "order_type": self.order_type,
            "maker_taker": self.maker_taker,
            "urgency_tier": self.urgency_tier,
            "repricing_logic": self.repricing_logic,
            "timeout_s": self.timeout_s,
            "exit_doctrine": self.exit_doctrine,
            "expected_fill_quality": self.expected_fill_quality,
            "retry_policy": self.retry_policy,
            "cancel_replace_budget": self.cancel_replace_budget,
            "queue_quality": self.queue_quality,
            "meta": dict(self.meta),
        }


class ExecutionIntelligence:
    """Turns a selected strategy idea into a liquidity-aware execution plan."""

    def build_plan(
        self,
        proposal: StrategyProposal,
        *,
        world: WorldStateSnapshot,
        mission: MissionDecision,
    ) -> ExecutionPlan:
        if proposal.side not in {"buy", "sell"} or proposal.action == "hold" or proposal.target_notional_quote <= 0.0:
            return ExecutionPlan(
                instrument=proposal.instrument,
                side=proposal.side,
                actionable=False,
                target_notional_quote=0.0,
                target_size=0.0,
                max_slippage_bps=0.0,
                order_type="none",
                maker_taker="none",
                urgency_tier="none",
                repricing_logic="none",
                timeout_s=0.0,
                exit_doctrine="observe",
                expected_fill_quality=1.0,
                retry_policy="none",
                cancel_replace_budget=0,
                queue_quality=1.0,
                meta={"reason": "non_actionable_proposal"},
            )

        urgency = mission.urgency_bias
        liquidity = world.market_state.liquidity_regime
        execution_stress = world.execution_state.execution_stress
        volatility = world.market_state.volatility_regime
        if urgency == "high" or proposal.execution_sensitivity >= 0.7:
            maker_taker = "taker"
            order_type = "ioc"
        elif mission.mission in {"spread_capture", "low_risk_accumulation"} and liquidity in {"NORMAL", "DEEP"}:
            maker_taker = "maker"
            order_type = "post_only"
        else:
            maker_taker = "maker" if liquidity == "DEEP" and execution_stress <= 0.35 else "taker"
            order_type = "limit" if maker_taker == "maker" else "ioc"

        participation_limit = 0.10 if liquidity == "THIN" else 0.20 if liquidity == "NORMAL" else 0.35
        liquidity_cap = max(0.0, world.market_state.depth_notional) * participation_limit
        free_cap = world.portfolio_state.free_quote if proposal.side == "buy" else max(world.portfolio_state.exposure_quote, proposal.target_notional_quote)
        raw_notional = min(proposal.target_notional_quote, max(0.0, liquidity_cap) if liquidity_cap > 0.0 else proposal.target_notional_quote, max(0.0, free_cap) if free_cap > 0.0 else proposal.target_notional_quote)
        target_notional = max(0.0, raw_notional * mission.size_scale)
        reference_price = max(world.market_state.last_mid, 1e-9)
        target_size = target_notional / reference_price

        max_slippage = proposal.slippage_risk_bps + world.execution_state.slippage_bps
        if volatility == "HIGH_VOL":
            max_slippage += 2.0
        if liquidity == "THIN":
            max_slippage += 3.0
        if maker_taker == "taker":
            max_slippage += 1.0
        max_slippage = _clamp(max_slippage, 0.5, 25.0)

        timeout_s = 5.0 if urgency == "high" else 30.0 if maker_taker == "maker" else 10.0
        cancel_replace_budget = 1 if maker_taker == "taker" else 4 if urgency == "high" else 8
        queue_quality = _clamp(1.0 - execution_stress + (0.1 if maker_taker == "maker" else -0.05), 0.05, 1.0)
        expected_fill_quality = _clamp(
            (world.execution_state.fill_probability * 0.45)
            + ((1.0 - execution_stress) * 0.30)
            + ((1.0 - min(max_slippage / 25.0, 1.0)) * 0.25),
            0.05,
            1.0,
        )
        repricing_logic = "top_of_book_reprice" if maker_taker == "maker" else "one_shot_or_abort"
        retry_policy = "bounded_retries" if maker_taker == "maker" else "abort_after_ioc"
        if mission.mission == "momentum_extraction":
            exit_doctrine = "trail_with_momentum_decay"
        elif mission.mission == "mean_reversion_harvest":
            exit_doctrine = "exit_near_mid_reversion"
        elif mission.mission in {"preserve_capital", "risk_off_defense", "inventory_unwind"}:
            exit_doctrine = "de_risk_fast_if_fill"
        elif mission.mission == "carry_extraction":
            exit_doctrine = "hold_until_carry_window_expires"
        else:
            exit_doctrine = "adaptive_take_profit"

        return ExecutionPlan(
            instrument=proposal.instrument,
            side=proposal.side,
            actionable=target_notional > 0.0,
            target_notional_quote=target_notional,
            target_size=target_size,
            max_slippage_bps=max_slippage,
            order_type=order_type,
            maker_taker=maker_taker,
            urgency_tier=urgency,
            repricing_logic=repricing_logic,
            timeout_s=timeout_s,
            exit_doctrine=exit_doctrine,
            expected_fill_quality=expected_fill_quality,
            retry_policy=retry_policy,
            cancel_replace_budget=cancel_replace_budget,
            queue_quality=queue_quality,
            meta={
                "mission": mission.mission,
                "proposal_strategy": proposal.strategy,
                "liquidity_regime": liquidity,
                "volatility_regime": volatility,
            },
        )
