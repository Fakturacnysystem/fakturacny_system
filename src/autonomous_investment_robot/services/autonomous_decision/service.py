from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from autonomous_investment_robot.core.contracts import OpportunityAuctionReport


class AutonomousDecisionService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def evaluate(
        self,
        *,
        candidates: list[dict[str, Any]],
        capital_envelope: dict[str, Any],
        expectancy: dict[str, Any],
        runtime_ordering_allowed: bool,
    ) -> dict[str, Any]:
        ranked: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        positive_edge_count = 0
        rejected_positive_edge_count = 0
        live_candidates = 0
        same_side = 0
        sides = [str(candidate.get("side", "") or "") for candidate in candidates]
        if sides:
            dominant_side = max(set(sides), key=sides.count)
            same_side = sum(1 for side in sides if side == dominant_side)
        for candidate in candidates:
            net_edge = float(candidate.get("expected_net_edge_bps", 0.0) or 0.0)
            confidence = float(candidate.get("confidence", 0.0) or 0.0)
            quality = float(candidate.get("quality_of_edge", 0.0) or 0.0)
            capital_efficiency = float(candidate.get("capital_efficiency", 0.0) or 0.0)
            opportunity_decay = float(candidate.get("opportunity_decay", 0.0) or 0.0)
            live_enabled = bool(candidate.get("live_enabled", False))
            if net_edge > 0.0:
                positive_edge_count += 1
            crowding_penalty = 0.0 if same_side <= 1 else min(0.5, same_side / max(len(candidates), 1) - 0.25)
            uncertainty_discount = max(0.05, 1.0 - (1.0 - confidence) * 0.65)
            score = net_edge * max(0.05, quality) * max(0.1, capital_efficiency) * uncertainty_discount * max(0.1, opportunity_decay)
            score *= 1.0 - crowding_penalty
            score *= 1.0 if live_enabled else 0.5
            capped = float(candidate.get("target_notional", 0.0) or 0.0) <= float(capital_envelope.get("playbook_level_cap", 0.0) or 0.0)
            reasons = list(candidate.get("disable_reasons", []) or [])
            if not capped:
                reasons.append("playbook_cap_exceeded")
            if not runtime_ordering_allowed and live_enabled:
                reasons.append("runtime_ordering_blocked")
            row = {
                **candidate,
                "score": score,
                "crowding_penalty": crowding_penalty,
                "uncertainty_discount": uncertainty_discount,
                "capital_capped": capped,
                "admission_allowed": live_enabled and capped and runtime_ordering_allowed and net_edge > 0.0,
                "reasons": list(dict.fromkeys([*(candidate.get("reasons", []) or []), *reasons])),
            }
            if row["admission_allowed"]:
                ranked.append(row)
                live_candidates += 1
            else:
                rejected.append(row)
                if net_edge > 0.0:
                    rejected_positive_edge_count += 1
        ranked.sort(key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)
        rejected.sort(key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)
        selected = ranked[0] if ranked else None
        false_negative_rate = 0.0 if positive_edge_count <= 0 else rejected_positive_edge_count / max(positive_edge_count, 1)
        false_positive_rate = 0.0 if not ranked else sum(1 for row in ranked if float(row.get("expected_net_edge_bps", 0.0) or 0.0) <= 0.0) / max(len(ranked), 1)
        backlog_pressure = min(1.0, len(candidates) / max(int(self.settings.playbooks.max_backlog_candidates), 1))
        signal_crowding_score = 0.0 if not candidates else min(1.0, same_side / max(len(candidates), 1))
        report = OpportunityAuctionReport(
            ts=datetime.now(timezone.utc),
            selected_symbol=None if selected is None else str(selected.get("symbol", "")),
            selected_playbook=None if selected is None else str(selected.get("playbook", "")),
            selected_score=0.0 if selected is None else float(selected.get("score", 0.0) or 0.0),
            backlog_pressure=backlog_pressure,
            false_negative_rate=false_negative_rate,
            false_positive_rate=false_positive_rate,
            signal_crowding_score=signal_crowding_score,
            ranked_candidates=ranked,
            rejected_candidates=rejected,
            metadata={
                "live_candidates": live_candidates,
                "runtime_ordering_allowed": runtime_ordering_allowed,
                "expectancy_bps": float(expectancy.get("net_expectancy_bps", 0.0) or 0.0),
            },
        )
        reason_histogram: dict[str, int] = {}
        rejection_matrix: dict[str, list[str]] = {}
        for row in rejected:
            rejection_matrix[f"{row.get('symbol')}:{row.get('playbook')}"] = list(row.get("reasons", []) or [])
            for reason in row.get("reasons", []) or []:
                normalized = str(reason)
                reason_histogram[normalized] = reason_histogram.get(normalized, 0) + 1
        payload = asdict(report)
        return {
            "selected_candidate": selected,
            "opportunity_queue_snapshot": {
                "ts": payload["ts"],
                "ranked_candidates": ranked,
            },
            "decision_ranking_explainability": payload,
            "candidate_rejection_matrix": rejection_matrix,
            "opportunity_auction_report": payload,
            "opportunity_backlog_report": {
                "ts": payload["ts"],
                "backlog_pressure": backlog_pressure,
                "candidate_count": len(candidates),
                "selected_playbook": None if selected is None else selected.get("playbook"),
            },
            "false_negative_report": {
                "ts": payload["ts"],
                "false_negative_rate": false_negative_rate,
                "rejected_positive_edge_candidates": rejected_positive_edge_count,
                "positive_edge_candidates": positive_edge_count,
            },
            "false_positive_report": {
                "ts": payload["ts"],
                "false_positive_rate": false_positive_rate,
                "accepted_candidates": len(ranked),
            },
            "quality_of_edge_report": {
                "ts": payload["ts"],
                "selected_quality_of_edge": None if selected is None else selected.get("quality_of_edge"),
                "candidates": {f"{row.get('symbol')}:{row.get('playbook')}": row.get("quality_of_edge") for row in ranked + rejected},
            },
            "signal_crowding_report": {
                "ts": payload["ts"],
                "signal_crowding_score": signal_crowding_score,
                "dominant_side_share": 0.0 if not candidates else same_side / max(len(candidates), 1),
            },
            "no_trade_reason_histogram": reason_histogram,
            "opportunity_miss_journal": {
                "ts": payload["ts"],
                "missed_candidates": [
                    {
                        "symbol": row.get("symbol"),
                        "playbook": row.get("playbook"),
                        "score": row.get("score"),
                        "reasons": row.get("reasons"),
                    }
                    for row in rejected[:10]
                ],
            },
        }

