from __future__ import annotations

from autonomous_investment_robot.core.contracts import EdgeImmunityReport, FragilitySignature


def assess_fragility(
    *,
    symbol: str,
    ts: object,
    base_edge_bps: float,
    stressed_edge_bps: float,
    self_impact_penalty_bps: float,
    dominant_failure_modes: list[str],
    wait_value_score: float,
) -> tuple[FragilitySignature, EdgeImmunityReport]:
    survival = 0.0 if base_edge_bps <= 0.0 else max(0.0, stressed_edge_bps) / max(base_edge_bps, 1e-9)
    reality_gap = max(0.0, min(1.0, (base_edge_bps - stressed_edge_bps) / max(abs(base_edge_bps), 1.0)))
    fragility = max(0.0, min(1.0, 1.0 - survival + reality_gap * 0.5 + self_impact_penalty_bps / 40.0))
    signature = FragilitySignature(
        edge_survival_ratio=survival,
        fragility_index=fragility,
        reality_gap_score=reality_gap,
        dominant_failure_modes=dominant_failure_modes,
        metadata={"base_edge_bps": base_edge_bps, "stressed_edge_bps": stressed_edge_bps},
    )
    report = EdgeImmunityReport(
        symbol=symbol,
        ts=ts,  # type: ignore[arg-type]
        base_expected_edge_bps=base_edge_bps,
        stressed_expected_edge_bps=stressed_edge_bps,
        edge_survival_ratio=survival,
        fragility_index=fragility,
        self_impact_penalty_bps=self_impact_penalty_bps,
        reality_gap_score=reality_gap,
        wait_value_score=wait_value_score,
        no_trade_quality=max(0.0, min(1.0, fragility * 0.7 + wait_value_score / 10.0)),
        dominant_failure_modes=dominant_failure_modes,
        recommended_size_multiplier=max(0.1, min(1.0, 1.0 - fragility)),
        recommended_execution_style="passive_limit" if fragility >= 0.45 else "unchanged",
        partial=False,
        metadata={"heuristic": True},
    )
    return signature, report
