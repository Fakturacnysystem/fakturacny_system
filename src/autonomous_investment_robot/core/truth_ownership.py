from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from autonomous_investment_robot.config.settings import ExecutionMode


class TruthDomain(str, Enum):
    BALANCE = "balance_truth"
    FILL = "fill_truth"
    ORDER = "order_truth"
    POSITION = "position_truth"
    FEE = "fee_truth"
    REALIZED_PNL = "realized_pnl_truth"
    UNREALIZED_PNL = "unrealized_pnl_truth"
    EXPOSURE = "exposure_truth"
    RISK_DECISION = "risk_decision_truth"
    EXECUTION_DECISION = "execution_decision_truth"
    CONFIGURATION = "configuration_truth"
    ENVIRONMENT = "environment_variable_truth"
    RUNTIME_MODE = "runtime_mode_truth"
    RISK_MODE = "risk_mode_truth"
    LIVE_GATING_STATUS = "live_gating_status_truth"
    RECONCILIATION_STATUS = "reconciliation_status_truth"


class TruthAuthority(str, Enum):
    AUTHORITATIVE = "authoritative"
    DERIVED = "derived"
    GAP = "gap"


@dataclass(frozen=True)
class TruthOwnership:
    domain: TruthDomain
    owner: str
    authority: TruthAuthority
    write_path: str
    read_path: str
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "domain": self.domain.value,
            "owner": self.owner,
            "authority": self.authority.value,
            "write_path": self.write_path,
            "read_path": self.read_path,
            "note": self.note,
        }


def _paper_ownership_map() -> list[TruthOwnership]:
    return [
        TruthOwnership(
            domain=TruthDomain.BALANCE,
            owner="RobotOrchestrator.paper_equity_model",
            authority=TruthAuthority.DERIVED,
            write_path="core/orchestrator.py::boot (equity variable)",
            read_path="risk_engine.evaluate(daily_loss_pct, drawdown_pct), ops.pnl",
            note="Paper mode has synthetic equity, not exchange cash balances.",
        ),
        TruthOwnership(
            domain=TruthDomain.FILL,
            owner="OMSService.apply_fill (accepted fills only)",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/oms/service.py::apply_fill",
            read_path="core/orchestrator.py::accepted_fills -> events_fills, accounting",
            note="Only OMS-accepted fills are allowed to affect accounting.",
        ),
        TruthOwnership(
            domain=TruthDomain.ORDER,
            owner="OMSService.orders state machine",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/oms/service.py::submit_intent/transition",
            read_path="core/orchestrator.py::ORDER_INTENT/ORDER_ACK lifecycle",
            note="Order lifecycle truth is explicit via state transitions.",
        ),
        TruthOwnership(
            domain=TruthDomain.POSITION,
            owner="RobotOrchestrator.paper_exposure_notional",
            authority=TruthAuthority.DERIVED,
            write_path="core/orchestrator.py::exposure accumulator",
            read_path="risk_engine.current_exposure, reconciliation.expected_exposure",
            note="Derived from accepted fills; reconciliation checks drift against fill-implied exposure.",
        ),
        TruthOwnership(
            domain=TruthDomain.FEE,
            owner="ExecutionService.execute_paper fill fee model",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/execution/service.py::Fill.fee/slippage_cost",
            read_path="core/orchestrator.py::fees aggregation",
            note="Paper fees/slippage come from deterministic execution cost model.",
        ),
        TruthOwnership(
            domain=TruthDomain.REALIZED_PNL,
            owner="RobotOrchestrator.paper_pnl_formula",
            authority=TruthAuthority.DERIVED,
            write_path="core/orchestrator.py::pnl calculation",
            read_path="equity updates, risk return history, trade_log",
            note="Calculated from accepted fills, fees, slippage, and funding proxy.",
        ),
        TruthOwnership(
            domain=TruthDomain.UNREALIZED_PNL,
            owner="UNASSIGNED_GAP",
            authority=TruthAuthority.GAP,
            write_path="N/A",
            read_path="N/A",
            note="Paper mode currently has no explicit unrealized PnL ledger.",
        ),
        TruthOwnership(
            domain=TruthDomain.EXPOSURE,
            owner="RobotOrchestrator.paper_exposure_notional",
            authority=TruthAuthority.DERIVED,
            write_path="core/orchestrator.py::exposure accumulator",
            read_path="risk_engine.current_exposure, ops.exposure_notional",
            note="Exposure is computed from accepted fills in paper mode.",
        ),
        TruthOwnership(
            domain=TruthDomain.RISK_DECISION,
            owner="RiskEngineService.evaluate",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/risk_engine/service.py::evaluate",
            read_path="core/orchestrator.py::risk decision gating",
            note="Risk decision reason code and adjusted_notional are canonical.",
        ),
        TruthOwnership(
            domain=TruthDomain.EXECUTION_DECISION,
            owner="ExecutionService.execute_paper",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/execution/service.py::execute_paper",
            read_path="core/orchestrator.py::fills/result accounting gate",
            note="Execution result controls whether an order mutates trade/accounting state.",
        ),
        TruthOwnership(
            domain=TruthDomain.CONFIGURATION,
            owner="RobotSettings.from_file + OpsService.track_config",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="config/settings.py::RobotSettings",
            read_path="orchestrator boot and run artifacts config hash",
            note="Config file values are parsed once and tracked with immutable hash in run_dir.",
        ),
        TruthOwnership(
            domain=TruthDomain.ENVIRONMENT,
            owner="OS environment (validated by RobotSettings and services)",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="process environment + shell scripts",
            read_path="config/settings.py validation + service initializers",
            note="Environment variables are explicit operator-controlled inputs with validation gates.",
        ),
        TruthOwnership(
            domain=TruthDomain.RUNTIME_MODE,
            owner="RobotSettings.execution_mode_enum",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="config/settings.py::execution_mode_enum",
            read_path="orchestrator branch: paper/live_readonly/live_testnet/live",
            note="Runtime mode selection is explicit and drives kill/live gating behavior.",
        ),
        TruthOwnership(
            domain=TruthDomain.RISK_MODE,
            owner="RiskEngineService.state.risk_mode",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/risk_engine/service.py::_set_risk_mode",
            read_path="risk decisions, health journal, ops metrics",
            note="Risk mode is an explicit state variable, not an inferred label.",
        ),
        TruthOwnership(
            domain=TruthDomain.LIVE_GATING_STATUS,
            owner="RobotSettings.live_gate_status",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="config/settings.py::live_gate_status",
            read_path="config manifest and operator runbooks",
            note="Paper mode still emits gate status so rollout intent is explicit even when ordering is disabled.",
        ),
        TruthOwnership(
            domain=TruthDomain.RECONCILIATION_STATUS,
            owner="ReconciliationService.reconcile_report",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/reconciliation/service.py::reconcile_report",
            read_path="reconciliation journals and operator gates",
            note="Paper reconciliation status is the canonical audit record for state agreement.",
        ),
    ]


def _live_ownership_map(provider_id: str) -> list[TruthOwnership]:
    provider = provider_id or "exchange_provider"
    return [
        TruthOwnership(
            domain=TruthDomain.BALANCE,
            owner=f"{provider}.balances endpoint",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="connectors/cex/*::balances()",
            read_path="live cash checks (currently coarse)",
            note="Exchange is authoritative for available/total balance in live modes.",
        ),
        TruthOwnership(
            domain=TruthDomain.FILL,
            owner="LiveBinanceService/LiveKrakenService authoritative_fill_history",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/execution/live_*_service.py::authoritative_fill_history -> services/live_runtime/service.py::LiveLedgerCoordinator",
            read_path="events_fills.jsonl, portfolio rehydration, live reconciliation confidence",
            note="Live fills are normalized from exchange-native history endpoints and mirrored locally with idempotent fill IDs.",
        ),
        TruthOwnership(
            domain=TruthDomain.ORDER,
            owner=f"{provider} order status endpoints",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/execution/live_*_service.py::execute_intent",
            read_path="query_order/open_orders, dedupe, timeout decisions",
            note="Exchange order status is treated as canonical in live execution flow.",
        ),
        TruthOwnership(
            domain=TruthDomain.POSITION,
            owner=f"{provider}.position_risk endpoint",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="connectors/cex/*::position_risk()",
            read_path="live reconciliation, flatten logic",
            note="Exchange position state is canonical in live reconciliation.",
        ),
        TruthOwnership(
            domain=TruthDomain.FEE,
            owner="exchange-native trade history/account log fee fields",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/execution/live_*_service.py::authoritative_fill_history",
            read_path="events_fills.jsonl fee_authoritative flag, portfolio account snapshot cumulative_fees",
            note="Fees come from exchange-native trade history; missing fee fields force flatten-only rather than silent approximation.",
        ),
        TruthOwnership(
            domain=TruthDomain.REALIZED_PNL,
            owner="LiveBinanceService/LiveKrakenService authoritative_realized_pnl + local fill ledger",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/execution/live_*_service.py::authoritative_realized_pnl and portfolio.record_fill(realized_pnl)",
            read_path="live reconciliation realized PnL sanity, account snapshots, learning records",
            note="Realized PnL is sourced from exchange-native income/account-history endpoints and mirrored fill-by-fill locally.",
        ),
        TruthOwnership(
            domain=TruthDomain.UNREALIZED_PNL,
            owner="RobotOrchestrator._live_loop internal mark-to-market",
            authority=TruthAuthority.DERIVED,
            write_path="core/orchestrator.py::_live_loop",
            read_path="risk drawdown/daily loss inputs",
            note="Currently estimated from internal exposure and mid-price deltas, not exchange PnL endpoints.",
        ),
        TruthOwnership(
            domain=TruthDomain.EXPOSURE,
            owner=f"{provider}.position_risk endpoint + ReconciliationService",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/execution/live_*_service.py::reconcile_live_state",
            read_path="risk_engine.current_exposure and flatten decisions",
            note="Exchange position notional and reconciliation are canonical for live exposure truth.",
        ),
        TruthOwnership(
            domain=TruthDomain.RISK_DECISION,
            owner="RiskEngineService.evaluate",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/risk_engine/service.py::evaluate",
            read_path="orchestrator live risk gate before execute_live",
            note="Risk reason codes and allowed/flatten flags are canonical in live mode.",
        ),
        TruthOwnership(
            domain=TruthDomain.EXECUTION_DECISION,
            owner="LiveBinanceService/LiveKrakenService execute_intent",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/execution/live_*_service.py::execute_intent",
            read_path="orchestrator live_exec status handling",
            note="Execution status/reason returned by live adapters is canonical for order outcome.",
        ),
        TruthOwnership(
            domain=TruthDomain.CONFIGURATION,
            owner="RobotSettings.from_file + OpsService.track_config",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="config/settings.py::RobotSettings",
            read_path="preflight/live guardrails and run artifact config hash",
            note="Live and paper behavior is constrained by validated settings + tracked config hash.",
        ),
        TruthOwnership(
            domain=TruthDomain.ENVIRONMENT,
            owner="OS environment (validated by RobotSettings and connectors)",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="process environment + shell scripts",
            read_path="API credential checks, live unlock gates, provider env var mapping",
            note="Environment validation is fail-closed for live execution.",
        ),
        TruthOwnership(
            domain=TruthDomain.RUNTIME_MODE,
            owner="RobotSettings.execution_mode_enum",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="config/settings.py::execution_mode_enum",
            read_path="orchestrator branch + execution service mode dispatch",
            note="Runtime mode controls whether execution is simulation, readonly, testnet, or full live.",
        ),
        TruthOwnership(
            domain=TruthDomain.RISK_MODE,
            owner="RiskEngineService.state.risk_mode",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/risk_engine/service.py::_set_risk_mode",
            read_path="risk decisions, health journal, ops metrics",
            note="Risk mode is explicit and can be downgraded automatically, but never promoted automatically.",
        ),
        TruthOwnership(
            domain=TruthDomain.LIVE_GATING_STATUS,
            owner="RobotOrchestrator.boot LIVE_GATE_STATUS event",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="core/orchestrator.py::boot",
            read_path="events_truth.jsonl, config manifest, operator gates",
            note="Live gating truth combines settings, preflight, rollout stage, and restart-state confidence.",
        ),
        TruthOwnership(
            domain=TruthDomain.RECONCILIATION_STATUS,
            owner="ReconciliationService.reconcile_live_report",
            authority=TruthAuthority.AUTHORITATIVE,
            write_path="services/reconciliation/service.py::reconcile_live_report",
            read_path="live reconciliation journals, flatten/halt decisions",
            note="Typed reconciliation outcome is canonical for live mismatch handling.",
        ),
    ]


def ownership_map(mode: ExecutionMode, provider_id: str) -> list[TruthOwnership]:
    if mode == ExecutionMode.PAPER:
        return _paper_ownership_map()
    return _live_ownership_map(provider_id=provider_id)


def ownership_gaps(rows: list[TruthOwnership]) -> list[str]:
    return [row.domain.value for row in rows if row.authority == TruthAuthority.GAP]


def validate_ownership_map(rows: list[TruthOwnership]) -> list[str]:
    errors: list[str] = []
    by_domain: dict[TruthDomain, TruthOwnership] = {}
    for row in rows:
        if row.domain in by_domain:
            errors.append(f"duplicate_domain:{row.domain.value}")
        else:
            by_domain[row.domain] = row
        if not row.owner.strip():
            errors.append(f"missing_owner:{row.domain.value}")
    missing = sorted(d.value for d in TruthDomain if d not in by_domain)
    for domain in missing:
        errors.append(f"missing_domain:{domain}")
    return errors
