from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


@dataclass
class DataEvent:
    venue: str
    symbol: str
    ts: datetime
    payload: dict[str, Any]
    stale: bool = False


@dataclass
class FeatureVector:
    feature_version: str
    symbol: str
    ts: datetime
    values: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ForecastDistribution:
    model_version: str
    symbol: str
    ts: datetime
    horizon: str
    mu: float
    sigma: float
    entropy: float
    quantiles: dict[float, float]


@dataclass
class RegimeProbabilities:
    ts: datetime
    probabilities: dict[str, float]
    selected: str


@dataclass
class OrderIntent:
    symbol: str
    side: str
    qty: float
    reason: str
    max_slippage_bps: float


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    throttle: float = 1.0
    kill_action: str | None = None


@dataclass
class MarketSnapshot:
    symbol: str
    ts: datetime
    bid: float
    ask: float
    mid: float
    spread_bps: float
    depth_notional: float
    orderbook_imbalance: float = 0.0
    flow_imbalance: float = 0.0
    realized_vol: float = 0.0
    mark_price: float = 0.0
    secondary_price: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketHealthSnapshot:
    symbol: str
    ts: datetime
    feed_stale: bool
    sequence_ok: bool
    checksum_ok: bool
    symbol_health_score: float
    exchange_health_score: float
    market_quality_score: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RegimeAssessment:
    symbol: str
    ts: datetime
    label: str
    confidence: float
    persistence: float
    transition_probability: float
    degradation_warning: str | None = None
    evidence: dict[str, float] = field(default_factory=dict)


@dataclass
class ExpertSignal:
    expert_name: str
    symbol: str
    ts: datetime
    directional_probability: float
    follow_through_probability: float
    expected_move_bps: float
    stop_out_probability: float
    execution_risk: float
    expected_edge_bps: float
    confidence: float
    uncertainty: float
    regime_fit: float
    capacity_limit: float
    reasons: dict[str, Any] = field(default_factory=dict)


@dataclass
class NoTradeDecision:
    symbol: str
    ts: datetime
    reason: str
    reasons: list[str] = field(default_factory=list)
    expected_edge_bps: float = 0.0
    expected_cost_bps: float = 0.0
    confidence: float = 0.0
    uncertainty: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyDecision:
    symbol: str
    ts: datetime
    trade_allowed: bool
    side: str | None = None
    target_notional: float = 0.0
    expected_edge_bps: float = 0.0
    expected_cost_bps: float = 0.0
    expected_slippage_bps: float = 0.0
    expected_adverse_excursion_bps: float = 0.0
    expected_favorable_excursion_bps: float = 0.0
    confidence: float = 0.0
    uncertainty: float = 0.0
    regime_fit: float = 0.0
    capacity_limit: float = 0.0
    why: dict[str, Any] = field(default_factory=dict)
    no_trade: NoTradeDecision | None = None
    profitability: dict[str, Any] = field(default_factory=dict)
    inventory: dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioAllocation:
    symbol: str
    ts: datetime
    recommended_notional: float
    concentration_score: float
    opportunity_cost_score: float
    volatility_scalar: float
    liquidity_scalar: float
    drawdown_scalar: float
    regime_scalar: float
    confidence_scalar: float
    uncertainty_scalar: float
    reasons: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionQualityForecast:
    symbol: str
    ts: datetime
    fill_probability: float
    expected_fill_speed_ms: int
    expected_price_quality_bps: float
    adverse_selection_risk: float
    passive_preferred: bool
    reasons: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    symbol: str
    ts: datetime
    side: str
    target_notional: float
    order_style: str
    passive: bool
    child_orders: int
    slippage_budget_bps: float
    max_participation_rate: float
    anti_chase_enabled: bool = True
    reasons: dict[str, Any] = field(default_factory=dict)
    reduce_only: bool = False


@dataclass
class PortfolioLedgerEntry:
    ts: datetime
    symbol: str
    entry_type: str
    quantity: float
    notional: float
    fee: float = 0.0
    slippage_cost: float = 0.0
    realized_pnl: float = 0.0
    venue: str = "paper"
    reference_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioStateSnapshot:
    ts: datetime
    symbol: str
    exposure_notional: float
    net_quantity: float
    cash_balance: float
    realized_pnl: float
    unrealized_pnl: float
    cumulative_fees: float
    cumulative_slippage: float
    fill_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InventoryLot:
    symbol: str
    venue: str
    side: str
    opened_ts: datetime
    remaining_notional: float
    entry_notional: float
    fees_paid: float = 0.0
    expected_exit_cost_bps: float = 0.0
    reserved_quote: float = 0.0
    source_fill_id: str = ""
    source_order_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReserveState:
    ts: datetime
    total_capital: float
    free_quote: float
    free_quote_reserve_pct: float
    minimum_reserve_pct: float
    reserve_breached: bool
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InventoryState:
    symbol: str
    ts: datetime
    open_lots: list[InventoryLot] = field(default_factory=list)
    gross_open_notional: float = 0.0
    stale_inventory_score: float = 0.0
    oldest_age_seconds: float = 0.0
    weighted_age_seconds: float = 0.0
    opportunity_cost_pressure: float = 0.0
    unrealized_draw_pressure: float = 0.0
    truth_fragility_pressure: float = 0.0
    execution_fragility_pressure: float = 0.0
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProfitFloorDecision:
    symbol: str
    ts: datetime
    threshold_bps: float
    base_threshold_bps: float
    raised_by_bps: float
    capital_release_allowed: bool = False
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapitalReleaseDecision:
    symbol: str
    ts: datetime
    action: str
    allowed: bool
    reason: str
    pressure_score: float
    recommended_notional: float = 0.0
    size_multiplier: float = 1.0
    reduce_only: bool = True
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExitIntent:
    symbol: str
    ts: datetime
    side: str
    target_notional: float
    reason: str
    reduce_only: bool = True
    execution_style: str = "passive_limit"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoundTripProfitabilityReport:
    symbol: str
    ts: datetime
    gross_edge_bps: float
    expected_entry_cost_bps: float
    expected_exit_cost_bps: float
    profit_floor_bps: float
    net_edge_bps: float
    viable: bool
    recommended_size_multiplier: float = 1.0
    action: str = "trade_now"
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountStateSnapshot:
    ts: datetime
    venue: str
    baseline_balance: float
    exchange_balance: float
    local_cash_delta: float
    realized_pnl: float
    unrealized_pnl: float
    gross_exposure_notional: float
    cumulative_fees: float
    cumulative_slippage: float
    fill_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class TruthConfidenceLevel(str, Enum):
    AUTHORITATIVE = "authoritative"
    PROXY = "proxy"
    UNAVAILABLE = "unavailable"


@dataclass
class TruthConfidence:
    domain: str
    level: TruthConfidenceLevel
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class UnrealizedPnlTruth:
    symbol: str
    ts: datetime
    source: str
    confidence: str
    venue_value: float | None = None
    local_value: float | None = None
    delta: float | None = None
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class TruthConfidenceSnapshot:
    ts: datetime
    fill_truth_confidence: TruthConfidence
    fee_truth_confidence: TruthConfidence
    realized_pnl_confidence: TruthConfidence
    balance_truth_confidence: TruthConfidence
    exposure_truth_confidence: TruthConfidence
    market_data_truth_confidence: TruthConfidence
    unrealized_pnl_confidence: TruthConfidence | None = None
    overall_action: str = "continue"
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetaGovernorDecision:
    symbol: str
    ts: datetime
    action: str
    size_multiplier: float = 1.0
    forced_risk_mode: str | None = None
    disabled_symbols: list[str] = field(default_factory=list)
    disabled_setups: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class OrderLifecycleState(str, Enum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    WORKING = "working"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    CANCEL_REJECTED = "cancel_rejected"
    REPLACE_PENDING = "replace_pending"
    REPLACED = "replaced"
    REPLACE_REJECTED = "replace_rejected"
    EXPIRED = "expired"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    STUCK = "stuck"
    ORPHANED = "orphaned"
    RECOVERED = "recovered"
    UNKNOWN = "unknown"


@dataclass
class OrderLifecycleTransition:
    symbol: str
    venue: str
    ts: datetime
    order_key: str
    from_state: str | None
    to_state: str
    source: str
    reason: str
    accepted: bool = True
    duplicate: bool = False
    out_of_order: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderLifecycleRecord:
    symbol: str
    venue: str
    order_key: str
    state: str
    confidence: str
    order_id: str = ""
    client_order_id: str = ""
    fill_count: int = 0
    last_event_ts: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountingDomainJudgment:
    domain: str
    ok: bool
    code: str
    severity: str
    action: str
    confidence: str
    delta: float | None = None
    tolerance: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AccountingJudgment:
    ok: bool
    code: str
    severity: str
    action: str
    domains: list[AccountingDomainJudgment] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryDecision:
    symbol: str
    ts: datetime
    outcome: str
    action: str
    confidence: str
    recovered_orders: int = 0
    orphan_orders: int = 0
    duplicate_repairs: int = 0
    out_of_order_repairs: int = 0
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningRecord:
    symbol: str
    ts: datetime
    regime_label: str
    confidence: float
    uncertainty: float
    intended_notional: float
    filled_notional: float
    expected_edge_bps: float
    realized_pnl: float
    mae_bps: float = 0.0
    mfe_bps: float = 0.0
    hold_seconds: float = 0.0
    exit_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TruthQualityWarning:
    domain: str
    level: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionCostAttribution:
    fee_cost: float
    slippage_cost: float
    observed_execution_cost_bps: float
    expected_execution_quality_bps: float | None = None
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeForensicsContext:
    symbol: str
    ts: datetime
    venue: str
    order_id: str
    side: str
    regime_label: str = ""
    policy_confidence: float = 0.0
    policy_uncertainty: float = 0.0
    expected_edge_bps: float = 0.0
    truth_confidence: dict[str, Any] = field(default_factory=dict)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    lifecycle: dict[str, Any] = field(default_factory=dict)
    unrealized_truth_source: str = ""
    inventory_age: float = 0.0
    profitability_context: dict[str, Any] = field(default_factory=dict)
    capital_release_context: dict[str, Any] = field(default_factory=dict)
    quantum_context: dict[str, Any] = field(default_factory=dict)
    edge_immunity_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PnLAttributionBreakdown:
    directional_pnl: float | None
    fee_pnl: float
    slippage_pnl: float
    holding_timing_pnl: float | None = None
    exit_timing_pnl: float | None = None
    execution_vs_signal_gap: float | None = None
    inventory_carry_cost: float | None = None
    truth_quality_penalty: float | None = None
    unexplained_pnl: float = 0.0
    partial: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class PnLAttributionRecord:
    symbol: str
    ts: datetime
    venue: str
    order_id: str
    side: str
    filled_notional: float
    realized_pnl: float
    expected_edge_bps: float
    expected_edge_pnl: float
    regime_label: str
    breakdown: PnLAttributionBreakdown
    execution_costs: ExecutionCostAttribution
    truth_warnings: list[TruthQualityWarning] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LossAutopsyReport:
    symbol: str
    ts: datetime
    venue: str
    category: str
    reason: str
    order_id: str = ""
    realized_pnl: float | None = None
    dominant_failure_modes: list[str] = field(default_factory=list)
    dominant_failure_chain: list[str] = field(default_factory=list)
    counterfactual_no_trade: bool | None = None
    counterfactual_wait: bool | None = None
    runtime_degradation_context: dict[str, Any] = field(default_factory=dict)
    truth_warnings: list[TruthQualityWarning] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    partial: bool = False


@dataclass
class PostTradeSummary:
    symbol: str
    ts: datetime
    venue: str
    order_id: str
    realized_pnl: float
    net_edge_bps: float
    outcome: str
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LossReviewSummary:
    symbol: str
    ts: datetime
    venue: str
    category: str
    reason: str
    severity: str
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioBranch:
    horizon: str
    label: str
    probability: float
    expected_move_bps: float
    expected_duration_minutes: float
    downside_risk_bps: float
    execution_fragility: float
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    probability: float
    horizon: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProbabilityField:
    symbol: str
    ts: datetime
    horizons: dict[str, dict[str, float]]
    entropy: float
    no_trade_probability: float
    execution_fragility_score: float
    confidence_decomposition: dict[str, float] = field(default_factory=dict)
    branch_disagreement_score: float = 0.0
    scenario_drift_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioTree:
    symbol: str
    ts: datetime
    branches: list[ScenarioBranch]
    transitions: list[StateTransition]
    probability_field: ProbabilityField
    dominant_state: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InterferenceScore:
    signal_name: str
    contribution: float
    agreement: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalInterferenceReport:
    symbol: str
    ts: datetime
    reinforcement_score: float
    conflict_score: float
    net_score: float
    uncertainty_penalty: float
    scores: list[InterferenceScore] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollapseDecisionContext:
    symbol: str
    ts: datetime
    scenario_tree: ScenarioTree
    interference_report: SignalInterferenceReport
    expected_move_distribution_bps: dict[str, float]
    uncertainty_decomposition: dict[str, float]
    no_trade_probability: float
    execution_fragility_score: float
    top_states: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollapseDecision:
    symbol: str
    ts: datetime
    recommended_action: str
    side: str | None
    action_score: float
    no_trade_probability: float
    execution_fragility_score: float
    size_multiplier: float
    expected_move_bps: float
    uncertainty: float
    branch_disagreement_score: float = 0.0
    scenario_drift_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QuantumState:
    symbol: str
    ts: datetime
    scenario_tree: ScenarioTree
    interference_report: SignalInterferenceReport
    collapse_context: CollapseDecisionContext
    collapse_decision: CollapseDecision
    heuristic: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CounterfactualWorld:
    name: str
    probability: float
    spread_multiplier: float
    depth_multiplier: float
    move_shock_bps: float
    volatility_multiplier: float
    self_impact_multiplier: float
    wait_edge_bonus_bps: float
    dominant_failure_mode: str
    fill_probability_multiplier: float = 1.0
    entry_delay_seconds: float = 0.0
    execution_style_hint: str = "unchanged"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FragilitySignature:
    edge_survival_ratio: float
    fragility_index: float
    reality_gap_score: float
    dominant_failure_modes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WaitDominanceReport:
    wait_value_score: float
    trade_now_score: float
    wait_dominant: bool
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeImmunityReport:
    symbol: str
    ts: datetime
    base_expected_edge_bps: float
    stressed_expected_edge_bps: float
    edge_survival_ratio: float
    fragility_index: float
    self_impact_penalty_bps: float
    reality_gap_score: float
    wait_value_score: float
    no_trade_quality: float
    dominant_failure_modes: list[str] = field(default_factory=list)
    recommended_size_multiplier: float = 1.0
    recommended_execution_style: str = "unchanged"
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeImmunityDecision:
    symbol: str
    ts: datetime
    action: str
    reason: str
    report: EdgeImmunityReport
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RealityFork:
    name: str
    probability: float
    edge_adjustment_bps: float
    execution_cost_penalty_bps: float
    dominant_failure_mode: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionEvaluation:
    action: str
    expected_utility_bps: float
    worst_case_bps: float
    regret_bps: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SPREDecision:
    symbol: str
    ts: datetime
    dominant_action: str
    side: str | None
    size_multiplier: float
    regret_score: float
    no_trade_quality: float
    narrative: str
    action_evaluations: list[ActionEvaluation] = field(default_factory=list)
    forks: list[RealityFork] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    heuristic: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ShadowRivalReport:
    symbol: str
    ts: datetime
    action: str
    allowed: bool
    critique_score: float
    reasons: list[str] = field(default_factory=list)
    narrative: str = ""
    heuristic: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionDoctrineReport:
    symbol: str
    ts: datetime
    recommended_action: str
    size_multiplier: float
    truth_strength: float
    survival_score: float
    robustness_score: float
    execution_survivability_score: float
    capital_freedom_score: float
    uncertainty_pressure: float
    partial_truth_penalty: float
    regret_pressure: float
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BackendSelector:
    backend: str
    enabled: bool = False
    reason: str = "single_process_default"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamEnvelope:
    stream: str
    ts: datetime
    key: str
    payload: dict[str, Any]
    version: str = "v1"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerJob:
    job_type: str
    ts: datetime
    job_id: str
    payload: dict[str, Any]
    required_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DistributedHealthReport:
    ts: datetime
    mode: str
    selector: BackendSelector
    stream_health: str = "disabled"
    storage_health: str = "disabled"
    worker_health: str = "disabled"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VenueConstraints:
    provider_id: str
    symbol: str
    min_order_size: float
    min_notional: float
    quantity_step: float
    price_tick: float
    maker_assumption: str
    taker_assumption: str
    reduce_only_supported: bool
    post_only_supported: bool
    replace_supported: bool
    expire_supported: bool
    confidence: str = "static_default"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderCapabilityMatrix:
    provider_id: str
    unrealized_pnl_truth_support: str
    realized_pnl_truth_support: str
    lifecycle_completeness: str
    replace_supported: bool
    expire_supported: bool
    fee_truth_confidence: str
    user_stream_confidence: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketIntegrityStatus:
    symbol: str
    provider_id: str
    ts: datetime
    score: float
    action: str
    confidence: str
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketWatchReport:
    symbol: str
    ts: datetime
    action: str
    score: float
    blackout_active: bool = False
    liquidity_score: float = 1.0
    spread_score: float = 1.0
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VenueLimitDecision:
    symbol: str
    provider_id: str
    ts: datetime
    action: str
    size_multiplier: float
    reduce_only_only: bool = False
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealthSnapshot:
    ts: datetime
    risk_mode: str
    health_score: float
    exchange_health_score: float
    market_quality_score: float
    execution_health_score: float
    drift_pressure: float
    anomaly_pressure: float
    overtrading_pressure: float
    action: str = "continue"
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapitalSovereigntyDecision:
    symbol: str
    ts: datetime
    action: str
    freedom_envelope_score: float
    reserve_pressure: float
    rotation_score: float
    recommended_size_multiplier: float
    keep_core_ratio: float
    satellite_ratio: float
    probe_ratio: float
    release_notional: float = 0.0
    rotate_notional: float = 0.0
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionMorphPlan:
    symbol: str
    ts: datetime
    action: str
    keep_core: bool
    trim_satellites: bool
    allow_runner: bool
    reduce_risk: bool
    core_fraction: float
    satellite_fraction: float
    runner_fraction: float
    add_notional: float = 0.0
    reduce_notional: float = 0.0
    probe_notional: float = 0.0
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdaptiveExitAllocation:
    symbol: str
    ts: datetime
    action: str
    core_exit_notional: float
    satellite_exit_notional: float
    runner_notional: float
    total_exit_notional: float
    execution_style: str
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyntheticAffectState:
    symbol: str
    ts: datetime
    confidence_state: float
    caution: float
    stress: float
    conviction: float
    fear: float
    asymmetry: float
    aggression_clamp: float
    no_trade_threshold_shift: float
    recommended_action: str
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceTrustAssessment:
    source_count: int
    average_trust: float
    weak_source_ratio: float
    trusted_sources: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FreshnessNoveltyAssessment:
    freshness_score: float
    novelty_score: float
    stale_event_ratio: float
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssetRelevanceAssessment:
    symbol: str
    relevance_score: float
    asset_overlap_score: float
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketImpactAssessment:
    impact_score: float
    sentiment_score: float
    expected_move_bps: float
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PricedInAssessment:
    priced_in_probability: float
    recommended_action: str
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdversarialNarrativeAssessment:
    adversarial_risk: float
    recommended_action: str
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataProvenanceEntry:
    symbol: str
    ts: datetime
    event_count: int
    provenance_completeness: float
    trusted_sources: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EventIntelligenceReport:
    symbol: str
    ts: datetime
    recommended_action: str
    overall_risk_score: float
    recommended_size_multiplier: float
    source_trust: SourceTrustAssessment
    freshness_novelty: FreshnessNoveltyAssessment
    asset_relevance: AssetRelevanceAssessment
    market_impact: MarketImpactAssessment
    priced_in: PricedInAssessment
    adversarial: AdversarialNarrativeAssessment
    provenance: DataProvenanceEntry
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityEvidence:
    provider_id: str
    ts: datetime
    evidence_freshness_seconds: float
    user_stream_connected: bool
    lifecycle_snapshot_count: int
    sequence_ok: bool
    checksum_ok: bool
    replace_support_evidence: str = "static"
    expire_support_evidence: str = "static"
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketIntegrityEvidence:
    symbol: str
    provider_id: str
    ts: datetime
    feed_age_seconds: float
    sequence_ok: bool
    checksum_ok: bool
    gap_count: int = 0
    checksum_mismatch_count: int = 0
    evidence_confidence: str = "partial"
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionSimulationScenario:
    name: str
    fill_probability: float
    expected_slippage_bps: float
    expected_cost_bps: float
    recommended_action: str
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionSimulationReport:
    symbol: str
    ts: datetime
    recommended_action: str
    recommended_execution_style: str
    expected_fill_probability: float
    stressed_fill_probability: float
    expected_slippage_bps: float
    worst_case_cost_bps: float
    scenarios: list[ExecutionSimulationScenario] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    partial: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeEpisode:
    symbol: str
    ts: datetime
    episode_id: str
    order_id: str
    side: str
    regime_label: str
    realized_pnl: float
    result: str
    truth_confidence_state: str
    execution_quality_state: str
    event_context: dict[str, Any] = field(default_factory=dict)
    failure_mode: str = ""
    attribution_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalogTradeMatch:
    episode_id: str
    similarity_score: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CounterfactualReview:
    symbol: str
    ts: datetime
    chosen_action: str
    best_alternative_action: str
    realized_regret: float
    avoided_regret: float
    similar_episodes: list[AnalogTradeMatch] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HumanEscalationDecision:
    symbol: str
    ts: datetime
    action: str
    severity: str
    manual_review_required: bool
    disagreement_score: float
    reasons: list[str] = field(default_factory=list)
    decision_key: str = ""
    acknowledged: bool = False
    acknowledgment_source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CalibrationProfile:
    ts: datetime
    recent_loss_rate: float
    recent_execution_miss_rate: float
    recent_truth_gap_rate: float
    no_trade_bias: float
    fragility_bias: float
    size_bias: float
    reasons: list[str] = field(default_factory=list)
    heuristic: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
