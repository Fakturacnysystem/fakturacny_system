from __future__ import annotations

from dataclasses import dataclass, field

from .execution import ExecutionPlan
from .mission import MissionDecision
from .parliament import ParliamentVerdict
from .state import WorldStateSnapshot


@dataclass(frozen=True)
class ShieldDecision:
    mode: str
    approved: bool
    size_scale: float
    reason_codes: list[str] = field(default_factory=list)
    kill_switch: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "approved": self.approved,
            "size_scale": self.size_scale,
            "reason_codes": list(self.reason_codes),
            "kill_switch": self.kill_switch,
        }


class UniverseShield:
    """Unified safety layer across model, execution, venue, and telemetry stress."""

    def assess(
        self,
        *,
        world: WorldStateSnapshot,
        mission: MissionDecision,
        verdict: ParliamentVerdict,
        plan: ExecutionPlan,
    ) -> ShieldDecision:
        reasons: list[str] = []
        if world.risk_state.hard_stop:
            return ShieldDecision(mode="hard-stop", approved=False, size_scale=0.0, reason_codes=["hard_stop_active"], kill_switch=True)
        if world.infra_state.stale_feed or world.infra_state.desync:
            reasons.extend(["stale_or_desync"])
            return ShieldDecision(mode="observe-only", approved=False, size_scale=0.0, reason_codes=reasons)
        if verdict.no_trade or mission.mission == "observation_only" or plan.actionable is False:
            reasons.extend(["no_trade_path"])
            return ShieldDecision(mode="observe-only", approved=False, size_scale=0.0, reason_codes=reasons)

        defensive_buy_block = plan.side == "buy"
        if (
            world.portfolio_state.drawdown_pct >= 0.15
            or world.execution_state.execution_stress >= 0.90
            or world.venue_state.cross_venue_divergence_bps >= 100.0
        ):
            reasons.extend(["catastrophic_stress"])
            return ShieldDecision(
                mode="hard-stop",
                approved=False,
                size_scale=0.0,
                reason_codes=reasons,
                kill_switch=True,
            )

        if (
            world.portfolio_state.drawdown_pct >= 0.08
            or world.execution_state.execution_stress >= 0.65
            or world.risk_state.observe_only
            or mission.allow_new_risk is False
        ):
            reasons.extend(["defensive_mode"])
            if defensive_buy_block:
                return ShieldDecision(mode="defensive", approved=False, size_scale=0.0, reason_codes=reasons)
            return ShieldDecision(mode="defensive", approved=True, size_scale=0.35, reason_codes=reasons)

        if (
            world.portfolio_state.drawdown_pct >= 0.04
            or world.execution_state.execution_stress >= 0.45
            or world.market_state.liquidity_regime == "THIN"
            or world.venue_state.funding_stress >= 0.70
            or world.confidence_score <= 0.45
        ):
            reasons.extend(["cautious_mode"])
            return ShieldDecision(mode="cautious", approved=True, size_scale=0.50, reason_codes=reasons)

        return ShieldDecision(mode="normal", approved=True, size_scale=1.0, reason_codes=["normal"])
