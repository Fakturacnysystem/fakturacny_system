from __future__ import annotations

from dataclasses import asdict, dataclass

from autonomous_investment_robot.services.execution.cost_engine import CostEngineService


@dataclass
class VenueCandidate:
    venue: str
    bid: float
    ask: float
    depth_notional: float
    fee_bps: float
    latency_ms: float
    stale_s: float
    queue_ahead_notional: float = 0.0
    maker_rebate_bps: float = 0.0


@dataclass
class RouteDecision:
    venue: str
    order_type: str
    expected_total_cost_bps: float
    expected_fill_prob: float
    expected_net_edge_bps: float
    reason: str
    diagnostics: dict[str, object]


class SmartOrderRouter:
    def __init__(self) -> None:
        self.cost = CostEngineService()

    def _queue_fill_prob(self, *, notional: float, queue_ahead_notional: float, latency_ms: float) -> float:
        queue = max(0.0, float(queue_ahead_notional))
        n = max(0.0, float(notional))
        lat = max(0.0, float(latency_ms))
        pressure = n / max(n + queue, 1e-9)
        latency_penalty = min(0.8, lat / 5000.0)
        return max(0.05, min(0.98, pressure * (1.0 - latency_penalty)))

    def _spread_bps(self, bid: float, ask: float) -> float:
        if bid <= 0.0 or ask <= 0.0:
            return 0.0
        mid = (bid + ask) / 2.0
        return ((ask - bid) / max(mid, 1e-9)) * 10000.0

    def pick_route(
        self,
        *,
        side: str,
        notional: float,
        expected_edge_bps: float,
        candidates: list[VenueCandidate],
        max_latency_ms: float = 2500.0,
        max_stale_s: float = 2.5,
        maker_preference: bool = True,
    ) -> RouteDecision | None:
        best: RouteDecision | None = None
        ranked: list[dict[str, object]] = []

        for cand in candidates:
            if cand.bid <= 0.0 or cand.ask <= 0.0:
                continue
            if cand.latency_ms > max_latency_ms or cand.stale_s > max_stale_s:
                continue

            spread_bps = self._spread_bps(cand.bid, cand.ask)
            maker_fill_prob = self._queue_fill_prob(
                notional=notional,
                queue_ahead_notional=cand.queue_ahead_notional,
                latency_ms=cand.latency_ms,
            )

            maker_cost = self.cost.estimate(
                notional=notional,
                depth_notional=cand.depth_notional,
                spread_bps=spread_bps,
                fee_bps=cand.fee_bps,
                slippage_bps=max(0.1, spread_bps * 0.18),
                maker=True,
            ).total_bps - max(0.0, cand.maker_rebate_bps)
            taker_cost = self.cost.estimate(
                notional=notional,
                depth_notional=cand.depth_notional,
                spread_bps=spread_bps,
                fee_bps=cand.fee_bps,
                slippage_bps=max(0.2, spread_bps * 0.35),
                maker=False,
            ).total_bps

            maker_net = expected_edge_bps - maker_cost
            taker_net = expected_edge_bps - taker_cost
            maker_expected = maker_net * maker_fill_prob

            choose_maker = maker_preference and maker_fill_prob >= 0.30 and maker_expected >= taker_net
            if choose_maker:
                order_type = "maker"
                expected_cost = maker_cost
                expected_fill_prob = maker_fill_prob
                expected_net = maker_expected
                reason = "maker_queue_advantage"
            else:
                order_type = "taker"
                expected_cost = taker_cost
                expected_fill_prob = 0.99
                expected_net = taker_net
                reason = "taker_urgency_or_cost"

            row = {
                "venue": cand.venue,
                "spread_bps": spread_bps,
                "maker_fill_prob": maker_fill_prob,
                "maker_cost_bps": maker_cost,
                "taker_cost_bps": taker_cost,
                "expected_net_edge_bps": expected_net,
                "order_type": order_type,
            }
            ranked.append(row)
            if expected_net <= 0.0:
                continue
            decision = RouteDecision(
                venue=cand.venue,
                order_type=order_type,
                expected_total_cost_bps=expected_cost,
                expected_fill_prob=expected_fill_prob,
                expected_net_edge_bps=expected_net,
                reason=reason,
                diagnostics=row,
            )
            if best is None or decision.expected_net_edge_bps > best.expected_net_edge_bps:
                best = decision

        if best is None:
            return None
        best.diagnostics = {
            **best.diagnostics,
            "ranked": sorted(ranked, key=lambda x: float(x.get("expected_net_edge_bps", -10**9)), reverse=True),
        }
        return best

    def plan_slices(self, *, target_notional: float, depth_notional: float, max_child_orders: int, max_participation_rate: float) -> list[float]:
        n = max(0.0, float(target_notional))
        if n <= 0.0:
            return []
        depth = max(1.0, float(depth_notional))
        cap = max(1.0, depth * max(0.01, min(1.0, float(max_participation_rate))))
        child = max(1, int(max_child_orders))
        child_size = min(cap, n / child)
        slices: list[float] = []
        rem = n
        while rem > 1e-9 and len(slices) < child:
            s = min(rem, child_size)
            slices.append(s)
            rem -= s
        if rem > 1e-9:
            slices[-1] += rem
        return slices

    def candidate_to_dict(self, candidate: VenueCandidate) -> dict[str, object]:
        return asdict(candidate)
