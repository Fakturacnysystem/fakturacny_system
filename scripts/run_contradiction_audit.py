#!/usr/bin/env python3
from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autonomous_investment_robot.config.settings import ExecutionSettings
from autonomous_investment_robot.services.edge_immunity_service.service import EdgeImmunityService
from autonomous_investment_robot.services.execution.service import ExecutionService
from autonomous_investment_robot.services.forensics_service.service import ForensicsService
from autonomous_investment_robot.services.market_integrity_service.service import MarketIntegrityService
from autonomous_investment_robot.services.oms.service import ManagedOrder, OMSService
from autonomous_investment_robot.services.policy.service import OrderIntent
from autonomous_investment_robot.services.reconciliation.service import ReconciliationService
from autonomous_investment_robot.services.shared_venue_limit_governor.service import SharedVenueLimitGovernor
from autonomous_investment_robot.services.venue_capability_registry.service import VenueCapabilityRegistry


def _result(name: str, ok: bool, details: dict[str, object]) -> dict[str, object]:
    return {"name": name, "ok": ok, "details": details}


def profitability_vs_risk() -> dict[str, object]:
    params = inspect.signature(ExecutionService.__init__).parameters
    risk_params = inspect.signature(__import__("autonomous_investment_robot.services.risk_engine.service", fromlist=["RiskEngineService"]).RiskEngineService.evaluate).parameters
    expected = {"free_quote_reserve_pct", "inventory_staleness_score", "capital_release_pressure", "round_trip_edge_bps"}
    return _result("profitability_vs_risk", expected.issubset(risk_params.keys()), {"risk_params_present": sorted(expected & set(risk_params.keys())), "execution_ctor_params": list(params.keys())})


def market_integrity_vs_venue_limits() -> dict[str, object]:
    capability = VenueCapabilityRegistry().resolve("kraken_derivatives")
    integrity = MarketIntegrityService().assess(
        symbol="BTCUSDT",
        provider_id="kraken_derivatives",
        snapshot=__import__("autonomous_investment_robot.core.contracts", fromlist=["MarketSnapshot"]).MarketSnapshot(
            symbol="BTCUSDT",
            ts=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            bid=100.0,
            ask=100.1,
            mid=100.05,
            spread_bps=10.0,
            depth_notional=1000.0,
        ),
        market_health=__import__("autonomous_investment_robot.core.contracts", fromlist=["MarketHealthSnapshot"]).MarketHealthSnapshot(
            symbol="BTCUSDT",
            ts=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            feed_stale=True,
            sequence_ok=True,
            checksum_ok=True,
            symbol_health_score=0.9,
            exchange_health_score=0.5,
            market_quality_score=0.8,
            reasons=["stale_feed"],
        ),
        capability=capability,
    )
    decision = SharedVenueLimitGovernor().evaluate(
        symbol="BTCUSDT",
        provider_id="kraken_derivatives",
        market_integrity=integrity,
        capability=capability,
    )
    ok = integrity.action in {"flatten_only", "halt"} and decision.action == "flatten_only" and decision.reduce_only_only is True
    return _result("market_integrity_vs_venue_limits", ok, {"integrity_action": integrity.action, "venue_limit_action": decision.action, "reasons": decision.reasons})


def oms_vs_lifecycle() -> dict[str, object]:
    oms = OMSService()
    order = ManagedOrder(order_id="audit-order", symbol="BTCUSDT", side="buy", notional=100.0, idempotency_key="audit")
    ok_submit, _ = oms.submit_intent(order)
    oms.transition("audit-order", "ACK")
    ok_fill, _ = oms.apply_fill("audit-order", 100.0, "fill-1")
    snapshot = oms.lifecycle_snapshot()
    return _result("oms_vs_lifecycle", ok_submit and ok_fill and any(item["state"] == "filled" for item in snapshot), {"snapshot": snapshot})


def lifecycle_vs_reconciliation() -> dict[str, object]:
    recon = ReconciliationService()
    judgment = recon.reconcile_lifecycle_judgment(
        lifecycle_snapshot=[{"state": "orphaned", "order_key": "abc"}],
        confidence="authoritative",
    )
    return _result("lifecycle_vs_reconciliation", judgment.code == "live_order_lifecycle_mismatch", {"judgment": judgment.code, "action": judgment.action})


def quantum_vs_policy_placeholder() -> dict[str, object]:
    # Policy integration is covered in tests; contradiction audit checks the explicit no-trade reason path remains present.
    policy_src = (REPO / "src" / "autonomous_investment_robot" / "services" / "policy" / "service.py").read_text(encoding="utf-8")
    ok = all(
        marker in policy_src
        for marker in [
            "quantum_branch_disagreement",
            "quantum_scenario_drift",
            "spre_no_trade_dominance",
            "shadow_rival_veto",
        ]
    )
    return _result("quantum_vs_policy", ok, {"reasons_present": ok})


def edge_vs_execution_planner() -> dict[str, object]:
    edge = EdgeImmunityService().evaluate(
        symbol="BTCUSDT",
        ts=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        features={"spread_proxy": 0.0015, "depth_notional": 10000.0},
        forecast=SimpleNamespace(mu=0.0001),
        regime_assessment=SimpleNamespace(label="liquidity_vacuum"),
        execution_quality=SimpleNamespace(fill_probability=0.25),
        portfolio_allocation=SimpleNamespace(recommended_notional=900.0),
        quantum_state=SimpleNamespace(collapse_decision=SimpleNamespace(expected_move_bps=5.0, execution_fragility_score=0.8, reasons=["fragile"])),
    )
    plan = ExecutionService(ExecutionSettings()).build_execution_plan(
        OrderIntent("BTCUSDT", "buy", 900.0, {}),
        depth_notional=10000.0,
        spread_bps=15.0,
        regime="RANGE",
        liquidity_regime="THIN",
    )
    ok = edge.action in {"trade_smaller", "wait", "no_trade"} and plan.order_style in {"limit", "marketable_limit"}
    return _result("edge_vs_execution_planner", ok, {"edge_action": edge.action, "plan_style": plan.order_style})


def forensics_vs_journals() -> dict[str, object]:
    run_dir = REPO / "runs" / "perps_intraday"
    required = ["pnl_attribution.jsonl", "loss_autopsy.jsonl", "post_trade_summary.jsonl", "loss_review_summary.jsonl"]
    present = {name: (run_dir / name).exists() for name in required}
    return _result("forensics_vs_live_journals", all(present.values()), present)


def operator_summaries_vs_sources() -> dict[str, object]:
    run_dir = REPO / "runs" / "perps_intraday"
    pairs = {
        "post_trade_summary.jsonl": "pnl_attribution.jsonl",
        "loss_review_summary.jsonl": "loss_autopsy.jsonl",
    }
    mismatches = []
    for summary, source in pairs.items():
        if (run_dir / summary).exists() and not (run_dir / source).exists():
            mismatches.append({"summary": summary, "source": source})
    return _result("operator_summaries_vs_sources", not mismatches, {"mismatches": mismatches})


def paper_semantics_vs_replay() -> dict[str, object]:
    ok = (REPO / "tests" / "fixtures" / "replay" / "golden_checksums_perps_intraday.json").exists()
    return _result("paper_semantics_vs_replay", ok, {"golden_fixture_present": ok})


def main() -> int:
    checks = [
        profitability_vs_risk(),
        market_integrity_vs_venue_limits(),
        oms_vs_lifecycle(),
        lifecycle_vs_reconciliation(),
        quantum_vs_policy_placeholder(),
        edge_vs_execution_planner(),
        forensics_vs_journals(),
        operator_summaries_vs_sources(),
        paper_semantics_vs_replay(),
    ]
    conflicts = [check for check in checks if not check["ok"]]
    report = {"checks": checks, "conflicts": conflicts}
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
