from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Mapping

from .events import UniverseEventEnvelope, build_event


WORLD_STATE_VERSION = "world_state_graph:v2"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(out):
        return float(default)
    return float(out)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _age(as_of: float, ts: float) -> float:
    if ts <= 0.0 or as_of <= 0.0:
        return 0.0
    return max(0.0, float(as_of) - float(ts))


@dataclass
class SymbolMarketState:
    symbol: str = ""
    venue: str = ""
    market_class: str = "crypto_spot"
    as_of_ts: float = 0.0
    event_ts: float = 0.0
    update_count: int = 0
    bid: float = 0.0
    ask: float = 0.0
    last_mid: float = 0.0
    spread_bps: float = 0.0
    realized_vol: float = 0.0
    depth_notional: float = 0.0
    trend_bias_bps: float = 0.0
    order_flow_aggression: float = 0.0
    trade_count: int = 0
    order_book_levels: int = 0
    candle_open: float = 0.0
    candle_high: float = 0.0
    candle_low: float = 0.0
    candle_close: float = 0.0
    candle_timeframe: str = ""
    regime: str = "RANGE"
    volatility_regime: str = "LOW_VOL"
    liquidity_regime: str = "NORMAL"
    expansion_state: str = "COMPRESSION"
    panic: bool = False
    regime_confidence: float = 0.5


@dataclass
class MarketState:
    as_of_ts: float = 0.0
    update_count: int = 0
    symbol: str = ""
    venue: str = ""
    market_class: str = "crypto_spot"
    primary_symbol: str = ""
    primary_venue: str = ""
    symbol_count: int = 0
    breadth_positive_ratio: float = 0.0
    last_mid: float = 0.0
    spread_bps: float = 0.0
    realized_vol: float = 0.0
    depth_notional: float = 0.0
    trend_bias_bps: float = 0.0
    order_flow_aggression: float = 0.0
    regime: str = "RANGE"
    volatility_regime: str = "LOW_VOL"
    liquidity_regime: str = "NORMAL"
    expansion_state: str = "COMPRESSION"
    panic: bool = False
    regime_confidence: float = 0.5
    symbols: dict[str, SymbolMarketState] = field(default_factory=dict)


@dataclass
class VenueHealthState:
    venue: str = ""
    as_of_ts: float = 0.0
    update_count: int = 0
    connectivity_status: str = "unknown"
    health_score: float = 1.0
    stale_feed: bool = False
    desync: bool = False
    degraded: bool = False
    latency_ms: float = 0.0
    ticker_age_s: float = 0.0
    book_age_s: float = 0.0
    trade_age_s: float = 0.0


@dataclass
class VenueState:
    as_of_ts: float = 0.0
    update_count: int = 0
    primary_venue: str = ""
    funding_rate: float = 0.0
    funding_stress: float = 0.0
    open_interest: float = 0.0
    open_interest_delta: float = 0.0
    cross_venue_divergence_bps: float = 0.0
    thick_thin_state: str = "THICK"
    venue_health_score: float = 1.0
    venues: dict[str, VenueHealthState] = field(default_factory=dict)


@dataclass
class AssetSnapshot:
    symbol: str = ""
    venue: str = ""
    market_class: str = "crypto_spot"
    as_of_ts: float = 0.0
    update_count: int = 0
    tradable: bool = True
    allow_trade: bool = True
    block_reasons: list[str] = field(default_factory=list)
    regime_hint: str = "RANGE"
    liquidity_band: str = "NORMAL"
    volatility_band: str = "LOW_VOL"
    microstructure_score: float = 0.5
    tradability_score: float = 1.0
    funding_rate: float = 0.0
    basis_bps: float = 0.0
    open_interest: float = 0.0
    cross_venue_divergence_bps: float = 0.0


@dataclass
class AssetState:
    as_of_ts: float = 0.0
    update_count: int = 0
    primary_symbol: str = ""
    assets: dict[str, AssetSnapshot] = field(default_factory=dict)


@dataclass
class PositionSnapshot:
    symbol: str = ""
    as_of_ts: float = 0.0
    update_count: int = 0
    base_qty: float = 0.0
    position_notional_quote: float = 0.0
    exposure_quote: float = 0.0
    avg_entry_price: float = 0.0
    realized_pnl_quote: float = 0.0
    unrealized_pnl_quote: float = 0.0
    inventory_pressure: float = 0.0


@dataclass
class PortfolioState:
    as_of_ts: float = 0.0
    update_count: int = 0
    equity_quote: float = 0.0
    free_quote: float = 0.0
    exposure_quote: float = 0.0
    exposure_ratio: float = 0.0
    drawdown_pct: float = 0.0
    realized_pnl_quote: float = 0.0
    unrealized_pnl_quote: float = 0.0
    available_margin_quote: float = 0.0
    concentration_score: float = 0.0
    inventory_pressure: float = 0.0
    own_account_stress: float = 0.0
    positions: dict[str, PositionSnapshot] = field(default_factory=dict)


@dataclass
class ExecutionSymbolState:
    symbol: str = ""
    as_of_ts: float = 0.0
    update_count: int = 0
    open_orders: int = 0
    recent_fills: int = 0
    rejection_count: int = 0
    fill_count: int = 0
    fill_ratio: float = 1.0
    rejection_ratio: float = 0.0
    slippage_bps: float = 0.0
    latency_ms: float = 0.0
    queue_quality: float = 1.0
    fill_probability: float = 1.0
    last_order_type: str = ""
    last_side: str = ""
    degradation_flags: list[str] = field(default_factory=list)


@dataclass
class ExecutionState:
    as_of_ts: float = 0.0
    update_count: int = 0
    open_orders_total: int = 0
    recent_fills_total: int = 0
    fill_ratio: float = 1.0
    rejection_ratio: float = 0.0
    slippage_bps: float = 0.0
    latency_ms: float = 0.0
    queue_quality: float = 1.0
    fill_probability: float = 1.0
    cancel_replace_load: float = 0.0
    execution_stress: float = 0.0
    degradation_flags: list[str] = field(default_factory=list)
    symbols: dict[str, ExecutionSymbolState] = field(default_factory=dict)


@dataclass
class InfraComponentState:
    component: str = ""
    as_of_ts: float = 0.0
    update_count: int = 0
    status: str = "unknown"
    health_score: float = 1.0
    stale: bool = False
    error_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InfraState:
    as_of_ts: float = 0.0
    update_count: int = 0
    health_status: str = "OK"
    stale_feed: bool = False
    desync: bool = False
    health_score: float = 1.0
    system_health_stress: float = 0.0
    runtime_mode: str = ""
    feature_posture: str = ""
    exception_counts: dict[str, int] = field(default_factory=dict)
    degraded_flags: list[str] = field(default_factory=list)
    components: dict[str, InfraComponentState] = field(default_factory=dict)


@dataclass
class RiskState:
    as_of_ts: float = 0.0
    update_count: int = 0
    mode: str = "normal"
    risk_flags: list[str] = field(default_factory=list)
    model_confidence: float = 0.5
    uncertainty_bps: float = 0.0
    hard_stop: bool = False
    observe_only: bool = False
    allow_trade: bool = True
    restrict_new_entries: bool = False
    exposure_posture: str = "normal"
    kill_switch_reason: str = ""
    per_symbol_flags: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class StrategyState:
    as_of_ts: float = 0.0
    update_count: int = 0
    last_mission: str = "observation_only"
    last_mission_confidence: float = 0.0
    last_mission_reason_codes: list[str] = field(default_factory=list)
    last_mission_transition_reason: str = ""
    mission_allowed_strategy_families: list[str] = field(default_factory=list)
    mission_execution_posture_hint: str = ""
    mission_shield_posture_hint: str = ""
    mission_is_conservative_fallback: bool = False
    mission_no_trade_preference: bool = False
    last_strategy: str = "no_trade_guardian"
    last_expected_value_bps: float = 0.0
    underperformance_streak: int = 0
    edge_available: bool = False
    no_trade_reason: str = ""
    latest_proposals: list[dict[str, Any]] = field(default_factory=list)
    selected_strategy_summary: dict[str, Any] = field(default_factory=dict)
    disagreement_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldStateMetadata:
    version: str = WORLD_STATE_VERSION
    as_of_ts: float = 0.0
    update_count: int = 0
    domain_update_counts: dict[str, int] = field(
        default_factory=lambda: {
            "market_state": 0,
            "venue_state": 0,
            "asset_state": 0,
            "portfolio_state": 0,
            "execution_state": 0,
            "infra_state": 0,
            "risk_state": 0,
            "strategy_state": 0,
        }
    )
    last_event_type: str = ""
    last_partition_key: str = ""
    last_source: str = ""
    graph_available: bool = True
    last_error: str = ""


@dataclass(frozen=True)
class SymbolStateSnapshot:
    symbol: str
    market: SymbolMarketState | None
    asset: AssetSnapshot | None
    position: PositionSnapshot | None
    execution: ExecutionSymbolState | None
    risk_flags: list[str]
    strategy: dict[str, Any]
    freshness_s: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "market": asdict(self.market) if self.market is not None else None,
            "asset": asdict(self.asset) if self.asset is not None else None,
            "position": asdict(self.position) if self.position is not None else None,
            "execution": asdict(self.execution) if self.execution is not None else None,
            "risk_flags": list(self.risk_flags),
            "strategy": dict(self.strategy),
            "freshness_s": dict(self.freshness_s),
        }


@dataclass(frozen=True)
class WorldStateSnapshot:
    as_of_time: float
    market_state: MarketState
    venue_state: VenueState
    asset_state: AssetState
    portfolio_state: PortfolioState
    execution_state: ExecutionState
    infra_state: InfraState
    risk_state: RiskState
    strategy_state: StrategyState
    metadata: WorldStateMetadata
    current_world_state: str
    confidence_score: float
    state_stability: float
    state_transition_probability: dict[str, float]

    def get_symbol_state(self, symbol: str) -> SymbolStateSnapshot:
        key = str(symbol or "").upper()
        market = self.market_state.symbols.get(key)
        asset = self.asset_state.assets.get(key)
        position = self.portfolio_state.positions.get(key)
        execution = self.execution_state.symbols.get(key)
        return SymbolStateSnapshot(
            symbol=key,
            market=market,
            asset=asset,
            position=position,
            execution=execution,
            risk_flags=list(self.risk_state.per_symbol_flags.get(key, [])),
            strategy={
                "last_mission": self.strategy_state.last_mission,
                "last_mission_confidence": self.strategy_state.last_mission_confidence,
                "last_mission_reason_codes": list(self.strategy_state.last_mission_reason_codes),
                "last_mission_transition_reason": self.strategy_state.last_mission_transition_reason,
                "mission_allowed_strategy_families": list(self.strategy_state.mission_allowed_strategy_families),
                "mission_execution_posture_hint": self.strategy_state.mission_execution_posture_hint,
                "mission_shield_posture_hint": self.strategy_state.mission_shield_posture_hint,
                "mission_is_conservative_fallback": self.strategy_state.mission_is_conservative_fallback,
                "mission_no_trade_preference": self.strategy_state.mission_no_trade_preference,
                "last_strategy": self.strategy_state.last_strategy,
                "selected_strategy_summary": dict(self.strategy_state.selected_strategy_summary),
                "no_trade_reason": self.strategy_state.no_trade_reason,
            },
            freshness_s={
                "market": _age(self.as_of_time, 0.0 if market is None else market.as_of_ts),
                "asset": _age(self.as_of_time, 0.0 if asset is None else asset.as_of_ts),
                "position": _age(self.as_of_time, 0.0 if position is None else position.as_of_ts),
                "execution": _age(self.as_of_time, 0.0 if execution is None else execution.as_of_ts),
            },
        )

    def freshness_by_domain(self) -> dict[str, float]:
        return {
            "market_state": _age(self.as_of_time, self.market_state.as_of_ts),
            "venue_state": _age(self.as_of_time, self.venue_state.as_of_ts),
            "asset_state": _age(self.as_of_time, self.asset_state.as_of_ts),
            "portfolio_state": _age(self.as_of_time, self.portfolio_state.as_of_ts),
            "execution_state": _age(self.as_of_time, self.execution_state.as_of_ts),
            "infra_state": _age(self.as_of_time, self.infra_state.as_of_ts),
            "risk_state": _age(self.as_of_time, self.risk_state.as_of_ts),
            "strategy_state": _age(self.as_of_time, self.strategy_state.as_of_ts),
        }

    def stale_domains(self, *, max_age_s: float) -> list[str]:
        threshold = max(0.0, float(max_age_s))
        return [domain for domain, age in self.freshness_by_domain().items() if age > threshold]

    def safe_to_trade(self, *, max_age_s: float = 30.0) -> bool:
        if not self.metadata.graph_available:
            return False
        if self.risk_state.hard_stop or self.risk_state.observe_only:
            return False
        if self.infra_state.stale_feed or self.infra_state.desync:
            return False
        critical = {
            "market_state",
            "portfolio_state",
            "execution_state",
            "infra_state",
            "risk_state",
        }
        stale = set(self.stale_domains(max_age_s=max_age_s))
        return not bool(critical & stale)

    def summary(self) -> dict[str, Any]:
        freshness = self.freshness_by_domain()
        return {
            "world_state_available": bool(self.metadata.graph_available),
            "world_state_as_of": float(self.as_of_time),
            "freshness_s": freshness,
            "stale_domains": self.stale_domains(max_age_s=30.0),
            "safe_to_trade": self.safe_to_trade(max_age_s=30.0),
            "market": {
                "primary_symbol": self.market_state.primary_symbol,
                "primary_venue": self.market_state.primary_venue,
                "regime": self.market_state.regime,
                "liquidity_regime": self.market_state.liquidity_regime,
                "volatility_regime": self.market_state.volatility_regime,
                "symbol_count": self.market_state.symbol_count,
                "breadth_positive_ratio": self.market_state.breadth_positive_ratio,
            },
            "venue": {
                "primary_venue": self.venue_state.primary_venue,
                "venue_health_score": self.venue_state.venue_health_score,
                "cross_venue_divergence_bps": self.venue_state.cross_venue_divergence_bps,
            },
            "portfolio": {
                "equity_quote": self.portfolio_state.equity_quote,
                "free_quote": self.portfolio_state.free_quote,
                "exposure_quote": self.portfolio_state.exposure_quote,
                "drawdown_pct": self.portfolio_state.drawdown_pct,
                "concentration_score": self.portfolio_state.concentration_score,
            },
            "execution": {
                "open_orders_total": self.execution_state.open_orders_total,
                "fill_ratio": self.execution_state.fill_ratio,
                "rejection_ratio": self.execution_state.rejection_ratio,
                "execution_stress": self.execution_state.execution_stress,
                "degradation_flags": list(self.execution_state.degradation_flags),
            },
            "infra": {
                "health_status": self.infra_state.health_status,
                "health_score": self.infra_state.health_score,
                "stale_feed": self.infra_state.stale_feed,
                "desync": self.infra_state.desync,
                "degraded_flags": list(self.infra_state.degraded_flags),
            },
            "risk": {
                "mode": self.risk_state.mode,
                "allow_trade": self.risk_state.allow_trade,
                "restrict_new_entries": self.risk_state.restrict_new_entries,
                "hard_stop": self.risk_state.hard_stop,
                "observe_only": self.risk_state.observe_only,
                "risk_flags": list(self.risk_state.risk_flags),
            },
            "strategy": {
                "last_mission": self.strategy_state.last_mission,
                "last_mission_confidence": self.strategy_state.last_mission_confidence,
                "last_mission_reason_codes": list(self.strategy_state.last_mission_reason_codes),
                "last_mission_transition_reason": self.strategy_state.last_mission_transition_reason,
                "mission_allowed_strategy_families": list(self.strategy_state.mission_allowed_strategy_families),
                "mission_execution_posture_hint": self.strategy_state.mission_execution_posture_hint,
                "mission_shield_posture_hint": self.strategy_state.mission_shield_posture_hint,
                "mission_is_conservative_fallback": self.strategy_state.mission_is_conservative_fallback,
                "mission_no_trade_preference": self.strategy_state.mission_no_trade_preference,
                "last_strategy": self.strategy_state.last_strategy,
                "edge_available": self.strategy_state.edge_available,
                "no_trade_reason": self.strategy_state.no_trade_reason,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_time": float(self.as_of_time),
            "market_state": asdict(self.market_state),
            "venue_state": asdict(self.venue_state),
            "asset_state": asdict(self.asset_state),
            "portfolio_state": asdict(self.portfolio_state),
            "execution_state": asdict(self.execution_state),
            "infra_state": asdict(self.infra_state),
            "risk_state": asdict(self.risk_state),
            "strategy_state": asdict(self.strategy_state),
            "metadata": asdict(self.metadata),
            "current_world_state": self.current_world_state,
            "confidence_score": self.confidence_score,
            "state_stability": self.state_stability,
            "state_transition_probability": dict(self.state_transition_probability),
            "summary": self.summary(),
        }


class WorldStateGraph:
    """Replay-safe, continuously updated internal model of market + self state."""

    def __init__(self) -> None:
        self.market_state = MarketState()
        self.venue_state = VenueState()
        self.asset_state = AssetState()
        self.portfolio_state = PortfolioState()
        self.execution_state = ExecutionState()
        self.infra_state = InfraState()
        self.risk_state = RiskState()
        self.strategy_state = StrategyState()
        self.metadata = WorldStateMetadata()

    def record_error(self, reason: str) -> None:
        self.metadata.graph_available = False
        self.metadata.last_error = str(reason or "")

    def clear_error(self) -> None:
        self.metadata.graph_available = True
        self.metadata.last_error = ""

    def apply(self, event: UniverseEventEnvelope) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        event_type = str(event.event_type or "").strip()
        event_ts = max(0.0, float(event.ts))
        symbol = str(payload.get("symbol", "") or "").upper()
        venue = str(payload.get("venue", "") or "").strip()
        try:
            if event_type in {"MarketTickEvent", "BookSnapshotEvent", "TradePrintEvent", "CandleEvent", "RegimeEvent"}:
                self._apply_market_update(event_type=event_type, payload=payload, event_ts=event_ts, symbol=symbol, venue=venue)
                self._sync_asset_state(symbol)
            if event_type in {"FundingEvent", "OpenInterestEvent", "CrossVenueEvent", "HealthEvent"}:
                self._apply_venue_update(event_type=event_type, payload=payload, event_ts=event_ts, venue=venue or self.market_state.primary_venue)
                self._sync_asset_state(symbol or self.market_state.primary_symbol)
            if event_type == "AccountSnapshotEvent":
                self._apply_account_update(payload=payload, event_ts=event_ts, symbol=symbol)
            elif event_type in {"OrderEvent", "FillEvent"}:
                self._apply_execution_update(event_type=event_type, payload=payload, event_ts=event_ts, symbol=symbol)
            elif event_type == "RiskEvent":
                self._apply_risk_update(payload=payload, event_ts=event_ts, symbol=symbol)
            elif event_type in {"MissionEvent", "StrategyProposalEvent", "ExecutionPlanEvent"}:
                self._apply_strategy_update(event_type=event_type, payload=payload, event_ts=event_ts, symbol=symbol)
            if event_type == "HealthEvent":
                self._apply_infra_update(payload=payload, event_ts=event_ts, component=str(payload.get("component", "marketdata") or "marketdata"))
            self._refresh_derived_state()
            self._touch_metadata(domain=self._domain_for_event(event_type), event=event)
            self.clear_error()
        except Exception as exc:
            self.record_error(str(exc))
            raise

    def apply_all(self, events: list[UniverseEventEnvelope]) -> None:
        for event in events:
            self.apply(event)

    def snapshot(self) -> WorldStateSnapshot:
        as_of = max(
            self.metadata.as_of_ts,
            self.market_state.as_of_ts,
            self.venue_state.as_of_ts,
            self.asset_state.as_of_ts,
            self.portfolio_state.as_of_ts,
            self.execution_state.as_of_ts,
            self.infra_state.as_of_ts,
            self.risk_state.as_of_ts,
            self.strategy_state.as_of_ts,
        )
        confidence = self._confidence_score()
        stability = self._state_stability()
        current = f"{self.market_state.regime}|{self.market_state.volatility_regime}|{self.market_state.liquidity_regime}"
        return WorldStateSnapshot(
            as_of_time=as_of,
            market_state=deepcopy(self.market_state),
            venue_state=deepcopy(self.venue_state),
            asset_state=deepcopy(self.asset_state),
            portfolio_state=deepcopy(self.portfolio_state),
            execution_state=deepcopy(self.execution_state),
            infra_state=deepcopy(self.infra_state),
            risk_state=deepcopy(self.risk_state),
            strategy_state=deepcopy(self.strategy_state),
            metadata=deepcopy(self.metadata),
            current_world_state=current,
            confidence_score=confidence,
            state_stability=stability,
            state_transition_probability=self._transition_probabilities(confidence=confidence, stability=stability),
        )

    def get_world_state(self) -> WorldStateSnapshot:
        return self.snapshot()

    def get_symbol_state(self, symbol: str) -> SymbolStateSnapshot:
        return self.snapshot().get_symbol_state(symbol)

    def get_portfolio_state(self) -> PortfolioState:
        return deepcopy(self.portfolio_state)

    def get_execution_summary(self) -> ExecutionState:
        return deepcopy(self.execution_state)

    def get_risk_posture(self) -> RiskState:
        return deepcopy(self.risk_state)

    def get_infra_health(self) -> InfraState:
        return deepcopy(self.infra_state)

    def get_strategy_meta_state(self) -> StrategyState:
        return deepcopy(self.strategy_state)

    def export_summary(self) -> dict[str, Any]:
        return self.snapshot().summary()

    def _apply_market_update(
        self,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        event_ts: float,
        symbol: str,
        venue: str,
    ) -> None:
        key = symbol or self.market_state.primary_symbol or "UNKNOWN"
        state = self.market_state.symbols.get(key, SymbolMarketState(symbol=key, venue=venue, market_class=str(payload.get("market_class", "crypto_spot") or "crypto_spot")))
        state.symbol = key
        state.venue = venue or state.venue or self.market_state.primary_venue
        state.market_class = str(payload.get("market_class", state.market_class) or state.market_class)
        state.as_of_ts = max(state.as_of_ts, event_ts)
        state.event_ts = event_ts
        state.update_count += 1
        if event_type == "MarketTickEvent":
            state.bid = max(0.0, _safe_float(payload.get("bid", state.bid), state.bid))
            state.ask = max(0.0, _safe_float(payload.get("ask", state.ask), state.ask))
            state.last_mid = _safe_float(payload.get("mid", payload.get("price", state.last_mid)), state.last_mid)
            state.spread_bps = max(0.0, _safe_float(payload.get("spread_bps", state.spread_bps), state.spread_bps))
            state.trend_bias_bps = _safe_float(payload.get("trend_bps", payload.get("trend_bias_bps", state.trend_bias_bps)), state.trend_bias_bps)
            state.realized_vol = max(0.0, _safe_float(payload.get("realized_vol", state.realized_vol), state.realized_vol))
        elif event_type == "BookSnapshotEvent":
            state.depth_notional = max(0.0, _safe_float(payload.get("depth_notional", state.depth_notional), state.depth_notional))
            state.spread_bps = max(0.0, _safe_float(payload.get("spread_bps", state.spread_bps), state.spread_bps))
            state.order_book_levels = max(0, _safe_int(payload.get("levels", state.order_book_levels), state.order_book_levels))
        elif event_type == "TradePrintEvent":
            state.trade_count += 1
            state.order_flow_aggression = _clamp(
                _safe_float(payload.get("aggression", payload.get("order_flow_aggression", state.order_flow_aggression)), state.order_flow_aggression),
                -1.0,
                1.0,
            )
            state.last_mid = _safe_float(payload.get("price", state.last_mid), state.last_mid)
        elif event_type == "CandleEvent":
            state.candle_open = _safe_float(payload.get("open", state.candle_open), state.candle_open)
            state.candle_high = _safe_float(payload.get("high", state.candle_high), state.candle_high)
            state.candle_low = _safe_float(payload.get("low", state.candle_low), state.candle_low)
            state.candle_close = _safe_float(payload.get("close", state.candle_close), state.candle_close)
            state.candle_timeframe = str(payload.get("timeframe", state.candle_timeframe) or state.candle_timeframe)
            if state.candle_close > 0.0:
                state.last_mid = state.candle_close
            if state.candle_open > 0.0 and state.candle_close > 0.0:
                state.trend_bias_bps = ((state.candle_close - state.candle_open) / max(state.candle_open, 1e-9)) * 10_000.0
            if state.candle_open > 0.0:
                state.realized_vol = max(
                    state.realized_vol,
                    abs(state.candle_high - state.candle_low) / max(state.candle_open, 1e-9),
                )
        elif event_type == "RegimeEvent":
            state.regime = str(payload.get("regime", state.regime) or state.regime)
            state.regime_confidence = _clamp(_safe_float(payload.get("confidence", state.regime_confidence), state.regime_confidence), 0.0, 1.0)
            state.volatility_regime = str(payload.get("volatility_regime", state.volatility_regime) or state.volatility_regime)
            state.liquidity_regime = str(payload.get("liquidity_regime", state.liquidity_regime) or state.liquidity_regime)
            state.expansion_state = str(payload.get("expansion_state", state.expansion_state) or state.expansion_state)
            state.panic = bool(payload.get("panic", state.panic))
        self._derive_symbol_market(state)
        self.market_state.symbols[key] = state
        self._refresh_market_state()

    def _apply_venue_update(
        self,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        event_ts: float,
        venue: str,
    ) -> None:
        name = venue or self.venue_state.primary_venue or "unknown"
        state = self.venue_state.venues.get(name, VenueHealthState(venue=name))
        state.venue = name
        state.as_of_ts = max(state.as_of_ts, event_ts)
        state.update_count += 1
        if event_type == "FundingEvent":
            self.venue_state.funding_rate = _safe_float(payload.get("funding_rate", self.venue_state.funding_rate), self.venue_state.funding_rate)
            self.venue_state.funding_stress = _clamp(abs(self.venue_state.funding_rate) * 500.0, 0.0, 1.0)
        elif event_type == "OpenInterestEvent":
            current_oi = _safe_float(payload.get("open_interest", self.venue_state.open_interest), self.venue_state.open_interest)
            prev_oi = self.venue_state.open_interest
            self.venue_state.open_interest = current_oi
            denom = max(abs(prev_oi), 1.0)
            self.venue_state.open_interest_delta = (current_oi - prev_oi) / denom
        elif event_type == "CrossVenueEvent":
            self.venue_state.cross_venue_divergence_bps = max(
                0.0,
                _safe_float(payload.get("divergence_bps", payload.get("cross_venue_divergence_bps", self.venue_state.cross_venue_divergence_bps)), self.venue_state.cross_venue_divergence_bps),
            )
        elif event_type == "HealthEvent":
            state.connectivity_status = str(payload.get("status", state.connectivity_status) or state.connectivity_status)
            state.stale_feed = bool(payload.get("stale_feed", state.stale_feed))
            state.desync = bool(payload.get("desync", state.desync))
            state.latency_ms = max(0.0, _safe_float(payload.get("latency_ms", state.latency_ms), state.latency_ms))
            state.health_score = _clamp(_safe_float(payload.get("health_score", state.health_score), state.health_score), 0.0, 1.0)
            state.degraded = bool(state.stale_feed or state.desync or state.health_score < 0.5)
            state.ticker_age_s = max(0.0, _safe_float(payload.get("ticker_age_s", state.ticker_age_s), state.ticker_age_s))
            state.book_age_s = max(0.0, _safe_float(payload.get("book_age_s", state.book_age_s), state.book_age_s))
            state.trade_age_s = max(0.0, _safe_float(payload.get("trade_age_s", state.trade_age_s), state.trade_age_s))
        self.venue_state.venues[name] = state
        self.venue_state.primary_venue = name
        self.venue_state.as_of_ts = max(self.venue_state.as_of_ts, event_ts)
        self.venue_state.update_count += 1
        self._refresh_venue_state()

    def _apply_account_update(self, *, payload: Mapping[str, Any], event_ts: float, symbol: str) -> None:
        self.portfolio_state.as_of_ts = max(self.portfolio_state.as_of_ts, event_ts)
        self.portfolio_state.update_count += 1
        self.portfolio_state.equity_quote = max(0.0, _safe_float(payload.get("equity_quote", self.portfolio_state.equity_quote), self.portfolio_state.equity_quote))
        self.portfolio_state.free_quote = max(0.0, _safe_float(payload.get("free_quote", self.portfolio_state.free_quote), self.portfolio_state.free_quote))
        self.portfolio_state.exposure_quote = max(0.0, _safe_float(payload.get("exposure_quote", self.portfolio_state.exposure_quote), self.portfolio_state.exposure_quote))
        self.portfolio_state.drawdown_pct = max(0.0, _safe_float(payload.get("drawdown_pct", self.portfolio_state.drawdown_pct), self.portfolio_state.drawdown_pct))
        self.portfolio_state.realized_pnl_quote = _safe_float(payload.get("realized_pnl_quote", self.portfolio_state.realized_pnl_quote), self.portfolio_state.realized_pnl_quote)
        self.portfolio_state.unrealized_pnl_quote = _safe_float(payload.get("unrealized_pnl_quote", self.portfolio_state.unrealized_pnl_quote), self.portfolio_state.unrealized_pnl_quote)
        self.portfolio_state.available_margin_quote = max(
            0.0,
            _safe_float(payload.get("available_margin_quote", payload.get("free_quote", self.portfolio_state.available_margin_quote)), self.portfolio_state.available_margin_quote),
        )
        if symbol:
            position = self.portfolio_state.positions.get(symbol, PositionSnapshot(symbol=symbol))
            position.symbol = symbol
            position.as_of_ts = max(position.as_of_ts, event_ts)
            position.update_count += 1
            position.base_qty = _safe_float(payload.get("base_qty", position.base_qty), position.base_qty)
            position.position_notional_quote = max(
                0.0,
                _safe_float(payload.get("position_notional_quote", payload.get("exposure_quote", position.position_notional_quote)), position.position_notional_quote),
            )
            position.exposure_quote = max(0.0, _safe_float(payload.get("exposure_quote", position.exposure_quote), position.exposure_quote))
            position.avg_entry_price = max(0.0, _safe_float(payload.get("avg_entry_price", position.avg_entry_price), position.avg_entry_price))
            position.realized_pnl_quote = _safe_float(payload.get("realized_pnl_quote", position.realized_pnl_quote), position.realized_pnl_quote)
            position.unrealized_pnl_quote = _safe_float(payload.get("unrealized_pnl_quote", position.unrealized_pnl_quote), position.unrealized_pnl_quote)
            position.inventory_pressure = _clamp(_safe_float(payload.get("inventory_pressure", position.inventory_pressure), position.inventory_pressure), 0.0, 1.0)
            self.portfolio_state.positions[symbol] = position
        self._refresh_portfolio_state()
        self._sync_asset_state(symbol)

    def _apply_execution_update(self, *, event_type: str, payload: Mapping[str, Any], event_ts: float, symbol: str) -> None:
        key = symbol or self.market_state.primary_symbol or "UNKNOWN"
        state = self.execution_state.symbols.get(key, ExecutionSymbolState(symbol=key))
        state.symbol = key
        state.as_of_ts = max(state.as_of_ts, event_ts)
        state.update_count += 1
        if event_type == "OrderEvent":
            state.open_orders = max(0, _safe_int(payload.get("open_orders", payload.get("open_orders_total", state.open_orders)), state.open_orders))
            state.last_order_type = str(payload.get("order_type", state.last_order_type) or state.last_order_type)
            state.last_side = str(payload.get("side", state.last_side) or state.last_side)
            state.rejection_count = max(0, _safe_int(payload.get("rejection_count", state.rejection_count), state.rejection_count))
            state.rejection_ratio = _clamp(_safe_float(payload.get("rejection_ratio", state.rejection_ratio), state.rejection_ratio), 0.0, 1.0)
            self.execution_state.cancel_replace_load = _clamp(
                _safe_float(payload.get("cancel_replace_load", self.execution_state.cancel_replace_load), self.execution_state.cancel_replace_load),
                0.0,
                1.0,
            )
            state.queue_quality = _clamp(_safe_float(payload.get("queue_quality", state.queue_quality), state.queue_quality), 0.0, 1.0)
        else:
            state.recent_fills += 1
            state.fill_count += 1
            state.fill_ratio = _clamp(_safe_float(payload.get("fill_ratio", state.fill_ratio), state.fill_ratio), 0.0, 1.0)
            state.slippage_bps = max(0.0, _safe_float(payload.get("slippage_bps", state.slippage_bps), state.slippage_bps))
            state.fill_probability = _clamp(_safe_float(payload.get("fill_probability", state.fill_probability), state.fill_probability), 0.0, 1.0)
            state.latency_ms = max(0.0, _safe_float(payload.get("latency_ms", state.latency_ms), state.latency_ms))
            state.rejection_count = max(0, _safe_int(payload.get("rejection_count", state.rejection_count), state.rejection_count))
            state.rejection_ratio = _clamp(_safe_float(payload.get("rejection_ratio", state.rejection_ratio), state.rejection_ratio), 0.0, 1.0)
        if state.rejection_ratio >= 0.5:
            state.degradation_flags.append("high_rejects")
        self.execution_state.symbols[key] = state
        self.execution_state.as_of_ts = max(self.execution_state.as_of_ts, event_ts)
        self.execution_state.update_count += 1
        self._refresh_execution_state()

    def _apply_infra_update(self, *, payload: Mapping[str, Any], event_ts: float, component: str) -> None:
        key = str(component or "runtime")
        state = self.infra_state.components.get(key, InfraComponentState(component=key))
        state.component = key
        state.as_of_ts = max(state.as_of_ts, event_ts)
        state.update_count += 1
        state.status = str(payload.get("status", state.status) or state.status)
        state.health_score = _clamp(_safe_float(payload.get("health_score", state.health_score), state.health_score), 0.0, 1.0)
        state.stale = bool(payload.get("stale_feed", payload.get("stale", state.stale)))
        state.metadata = {
            **dict(state.metadata),
            "latency_ms": max(0.0, _safe_float(payload.get("latency_ms", state.metadata.get("latency_ms", 0.0)), state.metadata.get("latency_ms", 0.0))),
            "rejection_ratio": _clamp(_safe_float(payload.get("rejection_ratio", state.metadata.get("rejection_ratio", 0.0)), state.metadata.get("rejection_ratio", 0.0)), 0.0, 1.0),
            "desync": bool(payload.get("desync", state.metadata.get("desync", False))),
        }
        self.infra_state.components[key] = state
        self.infra_state.as_of_ts = max(self.infra_state.as_of_ts, event_ts)
        self.infra_state.update_count += 1
        self._refresh_infra_state()

    def _apply_risk_update(self, *, payload: Mapping[str, Any], event_ts: float, symbol: str) -> None:
        self.risk_state.as_of_ts = max(self.risk_state.as_of_ts, event_ts)
        self.risk_state.update_count += 1
        flags = payload.get("risk_flags", self.risk_state.risk_flags)
        self.risk_state.risk_flags = [str(flag) for flag in flags] if isinstance(flags, list) else list(self.risk_state.risk_flags)
        self.risk_state.mode = str(payload.get("mode", self.risk_state.mode) or self.risk_state.mode)
        self.risk_state.model_confidence = _clamp(_safe_float(payload.get("model_confidence", self.risk_state.model_confidence), self.risk_state.model_confidence), 0.0, 1.0)
        self.risk_state.uncertainty_bps = max(0.0, _safe_float(payload.get("uncertainty_bps", self.risk_state.uncertainty_bps), self.risk_state.uncertainty_bps))
        self.risk_state.hard_stop = bool(payload.get("hard_stop", self.risk_state.hard_stop))
        self.risk_state.observe_only = bool(payload.get("observe_only", self.risk_state.observe_only))
        self.risk_state.kill_switch_reason = str(payload.get("kill_switch_reason", self.risk_state.kill_switch_reason) or self.risk_state.kill_switch_reason)
        if symbol:
            self.risk_state.per_symbol_flags[symbol] = list(self.risk_state.risk_flags)
        self._refresh_risk_state()
        self._sync_asset_state(symbol)

    def _apply_strategy_update(self, *, event_type: str, payload: Mapping[str, Any], event_ts: float, symbol: str) -> None:
        self.strategy_state.as_of_ts = max(self.strategy_state.as_of_ts, event_ts)
        self.strategy_state.update_count += 1
        if event_type == "MissionEvent":
            self.strategy_state.last_mission = str(
                payload.get("mission", payload.get("mission_type", self.strategy_state.last_mission)) or self.strategy_state.last_mission
            )
            self.strategy_state.last_mission_confidence = _clamp(
                _safe_float(payload.get("confidence", self.strategy_state.last_mission_confidence), self.strategy_state.last_mission_confidence),
                0.0,
                1.0,
            )
            reason_codes = payload.get("reason_codes", payload.get("rationale", self.strategy_state.last_mission_reason_codes))
            if isinstance(reason_codes, list):
                self.strategy_state.last_mission_reason_codes = [str(code) for code in reason_codes]
            self.strategy_state.last_mission_transition_reason = str(
                payload.get("transition_reason", self.strategy_state.last_mission_transition_reason) or self.strategy_state.last_mission_transition_reason
            )
            allowed_families = payload.get("allowed_strategy_families", self.strategy_state.mission_allowed_strategy_families)
            if isinstance(allowed_families, list):
                self.strategy_state.mission_allowed_strategy_families = [str(name) for name in allowed_families]
            self.strategy_state.mission_execution_posture_hint = str(
                payload.get("execution_posture_hint", self.strategy_state.mission_execution_posture_hint) or self.strategy_state.mission_execution_posture_hint
            )
            self.strategy_state.mission_shield_posture_hint = str(
                payload.get("shield_posture_hint", self.strategy_state.mission_shield_posture_hint) or self.strategy_state.mission_shield_posture_hint
            )
            self.strategy_state.mission_is_conservative_fallback = bool(
                payload.get("is_conservative_fallback", self.strategy_state.mission_is_conservative_fallback)
            )
            self.strategy_state.mission_no_trade_preference = bool(
                payload.get("no_trade_preferred", self.strategy_state.mission_no_trade_preference)
            )
            if self.strategy_state.last_mission == "observation_only":
                reason = self.strategy_state.last_mission_reason_codes[0] if self.strategy_state.last_mission_reason_codes else self.strategy_state.no_trade_reason
                self.strategy_state.no_trade_reason = str(reason or self.strategy_state.no_trade_reason)
        elif event_type == "StrategyProposalEvent":
            proposal = dict(payload)
            self.strategy_state.latest_proposals.append(proposal)
            self.strategy_state.latest_proposals = self.strategy_state.latest_proposals[-8:]
            self.strategy_state.last_strategy = str(payload.get("strategy", self.strategy_state.last_strategy) or self.strategy_state.last_strategy)
            self.strategy_state.last_expected_value_bps = _safe_float(payload.get("expected_value_bps", self.strategy_state.last_expected_value_bps), self.strategy_state.last_expected_value_bps)
            self.strategy_state.edge_available = bool(payload.get("expected_value_bps", 0.0) or payload.get("expected_edge_bps", 0.0))
        elif event_type == "ExecutionPlanEvent":
            self.strategy_state.selected_strategy_summary = {
                "symbol": symbol,
                "strategy": str(payload.get("strategy", self.strategy_state.last_strategy) or self.strategy_state.last_strategy),
                "side": str(payload.get("side", "")),
                "actionable": bool(payload.get("actionable", False)),
                "order_type": str(payload.get("order_type", "")),
                "urgency_tier": str(payload.get("urgency_tier", "")),
                "target_notional_quote": float(payload.get("target_notional_quote", 0.0) or 0.0),
            }
        self.strategy_state.last_strategy = str(
            self.strategy_state.selected_strategy_summary.get("strategy", self.strategy_state.last_strategy) or self.strategy_state.last_strategy
        )

    def _derive_symbol_market(self, state: SymbolMarketState) -> None:
        if state.regime == "RANGE":
            if abs(state.trend_bias_bps) >= 15.0:
                state.regime = "TREND"
            elif state.panic or state.realized_vol >= 0.03 or state.spread_bps >= 80.0:
                state.regime = "PANIC"
        state.volatility_regime = "HIGH_VOL" if state.realized_vol >= 0.015 or state.spread_bps >= 40.0 else "LOW_VOL"
        if state.depth_notional <= 0.0:
            state.liquidity_regime = "UNKNOWN"
        elif state.depth_notional < 1_000.0 or state.spread_bps >= 35.0:
            state.liquidity_regime = "THIN"
        elif state.depth_notional >= 10_000.0 and state.spread_bps <= 10.0:
            state.liquidity_regime = "DEEP"
        else:
            state.liquidity_regime = "NORMAL"
        state.expansion_state = "EXPANSION" if state.realized_vol >= 0.01 else "COMPRESSION"
        state.panic = bool(state.panic or state.regime == "PANIC")

    def _refresh_market_state(self) -> None:
        self.market_state.as_of_ts = max((row.as_of_ts for row in self.market_state.symbols.values()), default=self.market_state.as_of_ts)
        self.market_state.update_count += 1
        self.market_state.symbol_count = len(self.market_state.symbols)
        if not self.market_state.symbols:
            return
        freshest = max(self.market_state.symbols.values(), key=lambda row: (row.as_of_ts, row.update_count))
        positive = sum(1 for row in self.market_state.symbols.values() if row.trend_bias_bps > 0.0)
        self.market_state.breadth_positive_ratio = positive / max(len(self.market_state.symbols), 1)
        self.market_state.symbol = freshest.symbol
        self.market_state.venue = freshest.venue
        self.market_state.market_class = freshest.market_class
        self.market_state.primary_symbol = freshest.symbol
        self.market_state.primary_venue = freshest.venue
        self.market_state.last_mid = freshest.last_mid
        self.market_state.spread_bps = freshest.spread_bps
        self.market_state.realized_vol = freshest.realized_vol
        self.market_state.depth_notional = freshest.depth_notional
        self.market_state.trend_bias_bps = freshest.trend_bias_bps
        self.market_state.order_flow_aggression = freshest.order_flow_aggression
        self.market_state.regime = freshest.regime
        self.market_state.volatility_regime = freshest.volatility_regime
        self.market_state.liquidity_regime = freshest.liquidity_regime
        self.market_state.expansion_state = freshest.expansion_state
        self.market_state.panic = freshest.panic
        self.market_state.regime_confidence = freshest.regime_confidence

    def _refresh_venue_state(self) -> None:
        self.venue_state.as_of_ts = max((row.as_of_ts for row in self.venue_state.venues.values()), default=self.venue_state.as_of_ts)
        self.venue_state.update_count += 1
        if not self.venue_state.venues:
            return
        freshest = max(self.venue_state.venues.values(), key=lambda row: (row.as_of_ts, row.update_count))
        self.venue_state.primary_venue = freshest.venue
        self.venue_state.venue_health_score = _clamp(
            1.0 - max(self.venue_state.cross_venue_divergence_bps / 100.0, self.venue_state.funding_stress, 1.0 - freshest.health_score),
            0.0,
            1.0,
        )
        self.venue_state.thick_thin_state = "THIN" if self.market_state.liquidity_regime == "THIN" else "THICK"

    def _refresh_portfolio_state(self) -> None:
        self.portfolio_state.as_of_ts = max(
            self.portfolio_state.as_of_ts,
            max((row.as_of_ts for row in self.portfolio_state.positions.values()), default=self.portfolio_state.as_of_ts),
        )
        denom = max(self.portfolio_state.equity_quote, 1.0)
        self.portfolio_state.exposure_ratio = _clamp(self.portfolio_state.exposure_quote / denom, 0.0, 5.0)
        if self.portfolio_state.positions:
            biggest = max((row.position_notional_quote for row in self.portfolio_state.positions.values()), default=0.0)
            self.portfolio_state.concentration_score = _clamp(biggest / denom, 0.0, 1.0)
        self.portfolio_state.inventory_pressure = _clamp(
            max(self.portfolio_state.exposure_ratio, max((row.inventory_pressure for row in self.portfolio_state.positions.values()), default=0.0)),
            0.0,
            1.0,
        )
        free_ratio = min(self.portfolio_state.free_quote / denom, 1.0)
        self.portfolio_state.own_account_stress = _clamp(
            max(
                self.portfolio_state.drawdown_pct,
                self.portfolio_state.exposure_ratio * 0.40,
                self.portfolio_state.concentration_score * 0.75,
                1.0 - free_ratio,
            ),
            0.0,
            1.0,
        )

    def _refresh_execution_state(self) -> None:
        symbols = list(self.execution_state.symbols.values())
        self.execution_state.as_of_ts = max((row.as_of_ts for row in symbols), default=self.execution_state.as_of_ts)
        self.execution_state.update_count += 1
        self.execution_state.open_orders_total = sum(row.open_orders for row in symbols)
        self.execution_state.recent_fills_total = sum(row.recent_fills for row in symbols)
        if symbols:
            self.execution_state.fill_ratio = sum(row.fill_ratio for row in symbols) / len(symbols)
            self.execution_state.rejection_ratio = sum(row.rejection_ratio for row in symbols) / len(symbols)
            self.execution_state.slippage_bps = sum(row.slippage_bps for row in symbols) / len(symbols)
            self.execution_state.latency_ms = sum(row.latency_ms for row in symbols) / len(symbols)
            self.execution_state.queue_quality = sum(row.queue_quality for row in symbols) / len(symbols)
            self.execution_state.fill_probability = sum(row.fill_probability for row in symbols) / len(symbols)
        self.execution_state.execution_stress = _clamp(
            (
                (1.0 - self.execution_state.fill_ratio) * 0.30
                + self.execution_state.rejection_ratio * 0.35
                + min(self.execution_state.slippage_bps / 25.0, 1.0) * 0.20
                + min(self.execution_state.latency_ms / 500.0, 1.0) * 0.15
            ),
            0.0,
            1.0,
        )
        flags: list[str] = []
        if self.execution_state.rejection_ratio >= 0.35:
            flags.append("rejection_stress")
        if self.execution_state.slippage_bps >= 10.0:
            flags.append("slippage_shift")
        if self.execution_state.latency_ms >= 250.0:
            flags.append("latency_degraded")
        self.execution_state.degradation_flags = flags

    def _refresh_infra_state(self) -> None:
        components = list(self.infra_state.components.values())
        self.infra_state.as_of_ts = max((row.as_of_ts for row in components), default=self.infra_state.as_of_ts)
        self.infra_state.update_count += 1
        if components:
            health_avg = sum(row.health_score for row in components) / len(components)
            self.infra_state.health_score = _clamp(health_avg, 0.0, 1.0)
            self.infra_state.stale_feed = any(row.stale for row in components)
            self.infra_state.desync = any(bool(row.metadata.get("desync", False)) for row in components)
            self.infra_state.health_status = "WARN" if self.infra_state.stale_feed or self.infra_state.desync or health_avg < 0.5 else "OK"
        self.infra_state.system_health_stress = _clamp(
            max(
                1.0 - self.infra_state.health_score,
                1.0 if self.infra_state.stale_feed else 0.0,
                0.85 if self.infra_state.desync else 0.0,
            ),
            0.0,
            1.0,
        )
        flags: list[str] = []
        if self.infra_state.stale_feed:
            flags.append("stale_feed")
        if self.infra_state.desync:
            flags.append("desync")
        if self.infra_state.health_score < 0.50:
            flags.append("low_health")
        self.infra_state.degraded_flags = flags

    def _refresh_risk_state(self) -> None:
        if self.risk_state.hard_stop:
            self.risk_state.allow_trade = False
            self.risk_state.restrict_new_entries = True
            self.risk_state.exposure_posture = "hard_stop"
        elif self.risk_state.observe_only or self.risk_state.mode in {"observe-only", "defensive"}:
            self.risk_state.allow_trade = False
            self.risk_state.restrict_new_entries = True
            self.risk_state.exposure_posture = "defensive"
        else:
            self.risk_state.allow_trade = True
            self.risk_state.restrict_new_entries = False
            self.risk_state.exposure_posture = "normal"

    def _sync_asset_state(self, symbol: str) -> None:
        key = str(symbol or self.market_state.primary_symbol or "").upper()
        if not key:
            return
        market = self.market_state.symbols.get(key)
        existing = self.asset_state.assets.get(key, AssetSnapshot(symbol=key))
        asset = existing
        asset.symbol = key
        if market is not None:
            asset.venue = market.venue
            asset.market_class = market.market_class
            asset.as_of_ts = max(asset.as_of_ts, market.as_of_ts)
            asset.regime_hint = market.regime
            asset.liquidity_band = market.liquidity_regime
            asset.volatility_band = market.volatility_regime
            asset.cross_venue_divergence_bps = self.venue_state.cross_venue_divergence_bps
            asset.funding_rate = self.venue_state.funding_rate
            asset.open_interest = self.venue_state.open_interest
            asset.microstructure_score = _clamp(
                (1.0 - min(market.spread_bps / 100.0, 1.0)) * 0.40
                + min(market.depth_notional / 20_000.0, 1.0) * 0.40
                + (1.0 - abs(market.order_flow_aggression) * 0.20),
                0.0,
                1.0,
            )
        asset.allow_trade = self.risk_state.allow_trade and not self.infra_state.stale_feed
        asset.tradable = asset.allow_trade and self.metadata.graph_available
        block_reasons: list[str] = []
        if not self.risk_state.allow_trade:
            block_reasons.append("risk_restrict")
        if self.infra_state.stale_feed:
            block_reasons.append("stale_feed")
        if self.venue_state.cross_venue_divergence_bps >= 80.0:
            block_reasons.append("cross_venue_divergence")
        asset.block_reasons = block_reasons
        asset.tradability_score = _clamp(
            asset.microstructure_score * 0.40
            + self.venue_state.venue_health_score * 0.30
            + (1.0 - self.infra_state.system_health_stress) * 0.30,
            0.0,
            1.0,
        )
        asset.update_count += 1
        self.asset_state.assets[key] = asset
        self.asset_state.primary_symbol = key
        self.asset_state.as_of_ts = max(self.asset_state.as_of_ts, asset.as_of_ts)
        self.asset_state.update_count += 1
        self.metadata.domain_update_counts["asset_state"] = self.metadata.domain_update_counts.get("asset_state", 0) + 1

    def _refresh_derived_state(self) -> None:
        self._refresh_market_state()
        self._refresh_venue_state()
        self._refresh_portfolio_state()
        self._refresh_execution_state()
        self._refresh_infra_state()
        self._refresh_risk_state()
        if self.market_state.primary_symbol:
            self._sync_asset_state(self.market_state.primary_symbol)

    def _touch_metadata(self, *, domain: str, event: UniverseEventEnvelope) -> None:
        self.metadata.as_of_ts = max(self.metadata.as_of_ts, float(event.ts))
        self.metadata.update_count += 1
        self.metadata.domain_update_counts[domain] = self.metadata.domain_update_counts.get(domain, 0) + 1
        self.metadata.last_event_type = str(event.event_type)
        self.metadata.last_partition_key = str(event.partition_key)
        self.metadata.last_source = str(event.source)

    def _domain_for_event(self, event_type: str) -> str:
        if event_type in {"MarketTickEvent", "BookSnapshotEvent", "TradePrintEvent", "CandleEvent", "RegimeEvent"}:
            return "market_state"
        if event_type in {"FundingEvent", "OpenInterestEvent", "CrossVenueEvent"}:
            return "venue_state"
        if event_type == "AccountSnapshotEvent":
            return "portfolio_state"
        if event_type in {"OrderEvent", "FillEvent"}:
            return "execution_state"
        if event_type == "HealthEvent":
            return "infra_state"
        if event_type == "RiskEvent":
            return "risk_state"
        return "strategy_state"

    def _confidence_score(self) -> float:
        regime_conf = _clamp(self.market_state.regime_confidence, 0.0, 1.0)
        model_conf = _clamp(self.risk_state.model_confidence, 0.0, 1.0)
        infra_conf = _clamp(1.0 - self.infra_state.system_health_stress, 0.0, 1.0)
        exec_conf = _clamp(1.0 - self.execution_state.execution_stress, 0.0, 1.0)
        venue_conf = _clamp(self.venue_state.venue_health_score, 0.0, 1.0)
        return _clamp(
            regime_conf * 0.22 + model_conf * 0.22 + infra_conf * 0.18 + exec_conf * 0.18 + venue_conf * 0.10 + (1.0 - self.portfolio_state.own_account_stress) * 0.10,
            0.0,
            1.0,
        )

    def _state_stability(self) -> float:
        market_instability = _clamp(
            max(
                self.market_state.realized_vol * 20.0,
                self.market_state.spread_bps / 120.0,
                abs(self.market_state.order_flow_aggression) * 0.4,
                self.venue_state.cross_venue_divergence_bps / 120.0,
            ),
            0.0,
            1.0,
        )
        combined_instability = _clamp(
            market_instability * 0.40
            + self.execution_state.execution_stress * 0.18
            + self.portfolio_state.own_account_stress * 0.17
            + self.infra_state.system_health_stress * 0.15
            + (1.0 - self.venue_state.venue_health_score) * 0.10,
            0.0,
            1.0,
        )
        return _clamp(1.0 - combined_instability, 0.0, 1.0)

    def _transition_probabilities(self, *, confidence: float, stability: float) -> dict[str, float]:
        if self.market_state.regime == "PANIC":
            base = {"TREND": 0.10, "RANGE": 0.20, "PANIC": 0.70}
        elif self.market_state.regime == "TREND":
            base = {"TREND": 0.60, "RANGE": 0.25, "PANIC": 0.15}
        else:
            base = {"TREND": 0.25, "RANGE": 0.60, "PANIC": 0.15}
        stability_boost = _clamp((stability - 0.5) * 0.5, -0.20, 0.20)
        confidence_boost = _clamp((confidence - 0.5) * 0.4, -0.20, 0.20)
        if self.market_state.regime == "TREND":
            base["TREND"] = _clamp(base["TREND"] + stability_boost + confidence_boost, 0.05, 0.90)
            base["PANIC"] = _clamp(base["PANIC"] - confidence_boost, 0.05, 0.70)
        elif self.market_state.regime == "RANGE":
            base["RANGE"] = _clamp(base["RANGE"] + stability_boost, 0.05, 0.90)
            base["PANIC"] = _clamp(base["PANIC"] - confidence_boost, 0.05, 0.70)
        else:
            base["PANIC"] = _clamp(base["PANIC"] + (1.0 - stability) * 0.20, 0.10, 0.95)
            base["TREND"] = _clamp(base["TREND"] - (1.0 - stability) * 0.10, 0.02, 0.40)
        total = sum(base.values()) or 1.0
        return {key: value / total for key, value in base.items()}


class WorldStateStore:
    """Projection/store layer that updates the graph and exposes typed reads."""

    def __init__(self, graph: WorldStateGraph | None = None) -> None:
        self.graph = graph or WorldStateGraph()

    def apply_event(self, event: UniverseEventEnvelope) -> WorldStateSnapshot:
        self.graph.apply(event)
        return self.graph.snapshot()

    def apply_market_update(
        self,
        *,
        symbol: str,
        venue: str,
        payload: Mapping[str, Any],
        event_type: str = "MarketTickEvent",
        source: str = "world_state_store",
        ts: float | None = None,
    ) -> WorldStateSnapshot:
        return self.apply_event(
            build_event(
                event_type=event_type,
                source=source,
                partition_key=str(symbol).upper(),
                payload={"symbol": str(symbol).upper(), "venue": str(venue), **dict(payload)},
                ts=ts,
            )
        )

    def apply_account_update(
        self,
        *,
        symbol: str,
        venue: str,
        payload: Mapping[str, Any],
        source: str = "world_state_store",
        ts: float | None = None,
    ) -> WorldStateSnapshot:
        return self.apply_event(
            build_event(
                event_type="AccountSnapshotEvent",
                source=source,
                partition_key=str(symbol).upper(),
                payload={"symbol": str(symbol).upper(), "venue": str(venue), **dict(payload)},
                ts=ts,
            )
        )

    def apply_execution_update(
        self,
        *,
        symbol: str,
        venue: str,
        payload: Mapping[str, Any],
        event_type: str,
        source: str = "world_state_store",
        ts: float | None = None,
    ) -> WorldStateSnapshot:
        return self.apply_event(
            build_event(
                event_type=event_type,
                source=source,
                partition_key=str(symbol).upper(),
                payload={"symbol": str(symbol).upper(), "venue": str(venue), **dict(payload)},
                ts=ts,
            )
        )

    def apply_risk_update(
        self,
        *,
        symbol: str,
        venue: str,
        payload: Mapping[str, Any],
        source: str = "world_state_store",
        ts: float | None = None,
    ) -> WorldStateSnapshot:
        return self.apply_event(
            build_event(
                event_type="RiskEvent",
                source=source,
                partition_key=str(symbol).upper(),
                payload={"symbol": str(symbol).upper(), "venue": str(venue), **dict(payload)},
                ts=ts,
            )
        )

    def apply_telemetry_update(
        self,
        *,
        symbol: str,
        venue: str,
        payload: Mapping[str, Any],
        source: str = "world_state_store",
        ts: float | None = None,
    ) -> WorldStateSnapshot:
        return self.apply_event(
            build_event(
                event_type="HealthEvent",
                source=source,
                partition_key=str(symbol).upper(),
                payload={"symbol": str(symbol).upper(), "venue": str(venue), **dict(payload)},
                ts=ts,
            )
        )

    def apply_strategy_update(
        self,
        *,
        symbol: str,
        venue: str,
        payload: Mapping[str, Any],
        event_type: str,
        source: str = "world_state_store",
        ts: float | None = None,
    ) -> WorldStateSnapshot:
        return self.apply_event(
            build_event(
                event_type=event_type,
                source=source,
                partition_key=str(symbol).upper(),
                payload={"symbol": str(symbol).upper(), "venue": str(venue), **dict(payload)},
                ts=ts,
            )
        )

    def get_world_state(self) -> WorldStateSnapshot:
        return self.graph.get_world_state()

    def get_symbol_state(self, symbol: str) -> SymbolStateSnapshot:
        return self.graph.get_symbol_state(symbol)

    def get_portfolio_state(self) -> PortfolioState:
        return self.graph.get_portfolio_state()

    def get_execution_summary(self) -> ExecutionState:
        return self.graph.get_execution_summary()

    def get_risk_posture(self) -> RiskState:
        return self.graph.get_risk_posture()

    def get_infra_health(self) -> InfraState:
        return self.graph.get_infra_health()

    def get_strategy_meta_state(self) -> StrategyState:
        return self.graph.get_strategy_meta_state()

    def export_summary(self) -> dict[str, Any]:
        return self.graph.export_summary()
