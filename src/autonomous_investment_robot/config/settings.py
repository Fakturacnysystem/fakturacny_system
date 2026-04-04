from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

UNSPECIFIED = "UNSPECIFIED"
SUPPORTED_PROVIDER_IDS = frozenset({"binance_um_perps", "kraken_derivatives", "kraken_spot"})


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE_READONLY = "live_readonly"
    LIVE_TESTNET = "live_testnet"
    LIVE = "live"


class RolloutStage(str, Enum):
    PAPER = "paper"
    SHADOW = "shadow"
    TINY_LIVE = "tiny_live"
    CANARY_LIVE = "canary_live"
    LIMITED_LIVE = "limited_live"
    NORMAL_LIVE = "normal_live"


@dataclass
class RiskLimits:
    max_daily_loss_pct: float | str = UNSPECIFIED
    max_weekly_loss_pct: float | str = UNSPECIFIED
    max_drawdown_pct: float | str = UNSPECIFIED
    max_position_notional: float | str = UNSPECIFIED
    max_exposure_notional: float | str = UNSPECIFIED
    max_symbol_exposure_notional: float | str = UNSPECIFIED
    max_cluster_exposure_notional: float | str = UNSPECIFIED
    max_orders_per_min: int | str = UNSPECIFIED
    leverage: int | str = UNSPECIFIED
    target_portfolio_vol: float | str = UNSPECIFIED
    cvar_limit_pct: float | str = UNSPECIFIED
    stress_loss_limit_pct: float | str = UNSPECIFIED
    max_spread_bps: float | str = UNSPECIFIED
    min_depth_notional: float | str = UNSPECIFIED
    stale_data_seconds: float | str = UNSPECIFIED
    min_margin_buffer: float | str = UNSPECIFIED
    max_funding_cost_per_day: float | str = UNSPECIFIED
    max_oi_spike_pct: float | str = UNSPECIFIED
    max_liquidation_spike: float | str = UNSPECIFIED
    divergence_threshold_bps: float | str = UNSPECIFIED
    crowding_score_kill: float | str = UNSPECIFIED
    crowding_score_medium: float | str = UNSPECIFIED
    crowding_score_high: float | str = UNSPECIFIED
    crowding_score_extreme: float | str = UNSPECIFIED
    drawdown_cooldown_steps: int = 10
    drawdown_recovery_stable_steps: int = 5


@dataclass
class BinanceExecutionSettings:
    rest_base_url: str = "https://fapi.binance.com"
    ws_stream_base_url: str = "wss://fstream.binance.com"
    ws_user_base_url: str = "wss://fstream.binance.com"
    api_key_env: str = "EXCHANGE_API_KEY"
    api_secret_env: str = "EXCHANGE_API_SECRET"
    recv_window_ms: int = 5000
    request_timeout_s: float = 10.0
    rate_limit_rps: float = 8.0
    max_retries: int = 3
    backoff_base_ms: int = 200
    backoff_max_ms: int = 3000
    account_mode: str = "one_way"
    leverage_target: int = 1
    margin_type: str | None = None
    reduce_only_on_flatten: bool = True
    maker_preference: bool = True
    maker_timeout_s: int = 20
    taker_fallback: bool = True
    idempotency_salt_env: str | None = None
    allow_unknown_permissions: bool = False


@dataclass
class KrakenExecutionSettings:
    rest_base_url: str = "https://futures.kraken.com"
    ws_public_url: str = "wss://futures.kraken.com/ws/v1"
    api_key_env: str = "KRAKEN_API_KEY"
    api_secret_env: str = "KRAKEN_API_SECRET"
    request_timeout_s: float = 10.0
    rate_limit_rps: float = 5.0
    allow_unknown_permissions: bool = False
    reduce_only_on_flatten: bool = True


@dataclass
class KrakenSpotExecutionSettings:
    rest_base_url: str = "https://api.kraken.com"
    ws_public_url: str = "wss://ws.kraken.com/v2"
    ws_private_url: str = "wss://ws-auth.kraken.com/"
    api_key_env: str = "KRAKEN_SPOT_API_KEY"
    api_secret_env: str = "KRAKEN_SPOT_API_SECRET"
    request_timeout_s: float = 10.0
    rate_limit_rps: float = 3.0
    allow_unknown_permissions: bool = False
    event_feed_path: str = ""
    lifecycle_proof_enabled: bool = False
    lifecycle_proof_max_notional: float = 12.0
    lifecycle_proof_timeout_s: int = 3
    lifecycle_proof_min_free_quote_reserve_pct: float | None = None
    user_stream_connect_timeout_s: float = 3.0


@dataclass
class ExecutionSettings:
    mode: str = "paper"
    provider_id: str = "binance_um_perps"
    fee_bps: float = 2.0
    slippage_bps: float = 1.0
    partial_fill_ratio: float = 0.7
    maker_preference: bool = True
    maker_timeout_s: int = 30
    max_participation_rate: float = 0.1
    max_pct_volume: float = 0.1
    max_pct_top_depth: float = 0.12
    max_child_orders: int = 5
    slicing_parts: int = 2
    binance: BinanceExecutionSettings = field(default_factory=BinanceExecutionSettings)
    kraken: KrakenExecutionSettings = field(default_factory=KrakenExecutionSettings)
    kraken_spot: KrakenSpotExecutionSettings = field(default_factory=KrakenSpotExecutionSettings)


@dataclass
class LiveUnlockSettings:
    enable_live_trading: bool = False
    ack_i_understand_risks: bool = False
    require_testnet_passed: bool = True
    canary_required_before_full: bool = True
    allow_full_live_stage: bool = False


@dataclass
class SafetySettings:
    live_unlock: LiveUnlockSettings = field(default_factory=LiveUnlockSettings)


@dataclass
class PolicySettings:
    confidence_threshold: float = 0.55
    estimated_cost_bps: float = 3.0
    safety_buffer_bps: float = 1.0
    base_risk_budget: float = 1000.0
    min_free_quote_reserve_pct: float = 0.2
    stale_inventory_hours: float = 12.0
    capital_release_min_stale_score: float = 0.35


@dataclass
class DoctrineSettings:
    target_provider: str = ""
    product_target: str = ""
    long_only: bool = False
    never_open_new_short_exposure: bool = False
    minimum_sell_net_profit_bps: float = 120.0
    enforce_cost_basis_sell_block: bool = False
    enforce_net_profit_sell_block: bool = False
    block_non_reduce_only_sells: bool = False


@dataclass
class HarmonySettings:
    enabled: bool = False
    default_order_cadence_s: float = 5.0


@dataclass
class MarketWatchSettings:
    enabled: bool = False
    blackout_windows: list[dict[str, str]] = field(default_factory=list)
    entry_block_max_spread_bps: float = 35.0
    entry_degrade_max_spread_bps: float = 20.0
    entry_block_min_depth_notional: float = 10000.0
    entry_degrade_min_depth_notional: float = 25000.0
    liquidity_map_min_depth_notional: float = 25000.0
    block_new_entries_on_blackout: bool = True


@dataclass
class TCOSettings:
    max_total_cost_bps: float | str = UNSPECIFIED
    max_impact_bps: float | str = UNSPECIFIED


@dataclass
class RegimeSettings:
    panic_vol: float = 0.015
    panic_liquidations: float = 100000.0
    panic_funding_abs: float = 0.0005
    trend_ret3_abs: float = 0.004
    thin_spread: float = 0.01


@dataclass
class AllocatorSettings:
    max_weight_per_strategy: float = 0.7
    decay: float = 0.9
    min_samples: int = 3
    fatal_sigma_loss: float = 3.0
    cooldown_steps: int = 5


@dataclass
class MonitoringSettings:
    metrics_port: int = 9108
    decision_latency_warn_ms: float = 250.0
    reconciliation_lag_warn_ms: float = 1000.0
    loop_latency_warn_ms: float = 1000.0
    manual_review_ack_ttl_minutes: int = 240


@dataclass
class StorageSettings:
    run_dir: str = "runs/latest"


@dataclass
class FixtureSettings:
    ohlcv_csv: str = "data/fixtures/btcusdt_1h.csv"
    symbol_files: dict[str, str] = field(default_factory=dict)


@dataclass
class ReplaySettings:
    source: str = "fixtures"


@dataclass
class KrakenSpotNonLiveSettings:
    profile: str = "legacy"
    event_fixture_path: str = ""
    event_recording_path: str = ""
    emit_operator_bundle: bool = False
    emit_replay_bundle: bool = False


@dataclass
class MLOpsSettings:
    retrain_enabled: bool = True
    canary_risk_pct: float = 0.05
    rollback_dd_threshold_pct: float = 2.0
    drift_psi_threshold: float = 0.2


@dataclass
class PerformanceTargetSettings:
    monthly_return_pct: float = 30.0
    max_monthly_drawdown_pct: float = 10.0
    max_intraday_drawdown_pct: float = 3.0
    round_trips_per_day: float = 1.0
    capital_utilization_pct: float = 50.0
    net_bps_per_trade: float = 20.0
    expectancy_bps_floor: float = 5.0
    fill_rate: float = 0.35
    maker_ratio: float = 0.7
    max_inventory_age_minutes: float = 720.0


@dataclass
class CapitalEnvelopeSettings:
    max_pair_exposure_notional: float = 250.0
    reserve_fraction: float = 0.35
    max_portfolio_heat: float = 0.65
    max_regime_heat: float = 0.45
    max_playbook_heat: float = 0.30
    idle_capital_alert_threshold: float = 0.60
    target_capital_utilization_min: float = 0.35
    max_capital_lock_time_min: float = 720.0
    capital_efficiency_min_score: float = 0.40


@dataclass
class MarketUniverseSettings:
    pair_universe: list[str] = field(default_factory=list)
    max_active_pairs: int = 1
    pair_rotation_interval_s: int = 300
    pair_min_depth_notional: float = 25000.0
    pair_max_spread_bps: float = 35.0
    pair_min_expectancy_bps: float = 0.0
    pair_min_fill_rate: float = 0.0
    pair_clustering_enabled: bool = True
    pair_admission_lookback_trades: int = 10
    pair_expulsion_expectancy_floor_bps: float = -10.0


@dataclass
class PlaybookSettings:
    enable_multi_playbook_shadow: bool = True
    enable_multi_pair_shadow: bool = True
    live_candidate_auction_enabled: bool = True
    max_backlog_candidates: int = 12
    default_opportunity_half_life_s: int = 180
    signal_crowding_limit: float = 0.70
    shadow_only_playbooks: list[str] = field(
        default_factory=lambda: [
            "inventory_unwind",
            "profit_capture_exit",
        ]
    )


@dataclass
class ExpectancySettings:
    rolling_window_trades: int = 50
    min_sample_guard: int = 5
    size_down_expectancy_floor_bps: float = 0.0
    cooldown_expectancy_floor_bps: float = -10.0
    disable_expectancy_floor_bps: float = -20.0
    promotion_expectancy_bps: float = 8.0
    intraday_session_buckets: list[str] = field(
        default_factory=lambda: ["asia", "europe", "us", "overnight"]
    )


@dataclass
class ExperimentsSettings:
    enabled: bool = True
    evidence_min_trades: int = 5
    rollback_loss_bps: float = -25.0
    staged_variants_enabled: bool = True
    shadow_variant_bias: float = 0.20
    promotion_score_min: float = 0.60


@dataclass
class OperatorKPISettings:
    expose_advanced_runtime_panels: bool = True
    backlog_pressure_warn: float = 0.60
    capital_efficiency_warn: float = 0.40
    live_degradation_warn: float = 0.45
    false_negative_warn: float = 0.30
    false_positive_warn: float = 0.20


@dataclass
class MarginSettings:
    enabled: bool = False
    max_leverage: int = 0
    isolated_only: bool = True
    reduce_only_emergency: bool = True
    require_explicit_opt_in: bool = True


@dataclass
class RobotSettings:
    config_schema_version: int = 3
    trading_mode: TradingMode = TradingMode.PAPER
    explicit_live_enable: bool = False
    ack_live_risks: bool = False
    canary_mode: bool = False
    safe_mode_default: bool = True
    rollout_stage_override: str = ""
    provider_whitelist: list[str] = field(default_factory=list)
    universe: list[str] = field(default_factory=lambda: ["BTCUSDT"])
    timeframe: str = "1h"
    risk: RiskLimits = field(default_factory=RiskLimits)
    execution: ExecutionSettings = field(default_factory=ExecutionSettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    policy: PolicySettings = field(default_factory=PolicySettings)
    doctrine: DoctrineSettings = field(default_factory=DoctrineSettings)
    harmony: HarmonySettings = field(default_factory=HarmonySettings)
    market_watch: MarketWatchSettings = field(default_factory=MarketWatchSettings)
    tco: TCOSettings = field(default_factory=TCOSettings)
    regime: RegimeSettings = field(default_factory=RegimeSettings)
    allocator: AllocatorSettings = field(default_factory=AllocatorSettings)
    monitoring: MonitoringSettings = field(default_factory=MonitoringSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    fixtures: FixtureSettings = field(default_factory=FixtureSettings)
    replay: ReplaySettings = field(default_factory=ReplaySettings)
    kraken_spot_non_live: KrakenSpotNonLiveSettings = field(default_factory=KrakenSpotNonLiveSettings)
    mlops: MLOpsSettings = field(default_factory=MLOpsSettings)
    performance_targets: PerformanceTargetSettings = field(default_factory=PerformanceTargetSettings)
    capital_envelope: CapitalEnvelopeSettings = field(default_factory=CapitalEnvelopeSettings)
    market_universe: MarketUniverseSettings = field(default_factory=MarketUniverseSettings)
    playbooks: PlaybookSettings = field(default_factory=PlaybookSettings)
    expectancy: ExpectancySettings = field(default_factory=ExpectancySettings)
    experiments: ExperimentsSettings = field(default_factory=ExperimentsSettings)
    operator_kpis: OperatorKPISettings = field(default_factory=OperatorKPISettings)
    margin: MarginSettings = field(default_factory=MarginSettings)

    @classmethod
    def from_env(cls) -> "RobotSettings":
        mode = TradingMode(os.getenv("ROBOT_TRADING_MODE", "paper"))
        explicit = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
        ack = os.getenv("ACK_I_UNDERSTAND_RISKS", "false").lower() == "true"
        canary = os.getenv("CANARY_MODE", "false").lower() == "true"
        safe = os.getenv("ROBOT_SAFE_MODE_DEFAULT", "true").lower() == "true"
        providers = [p for p in os.getenv("ROBOT_PROVIDER_WHITELIST", "").split(",") if p]
        exec_mode = os.getenv("ROBOT_EXECUTION_MODE", "paper")
        return cls(
            trading_mode=mode,
            explicit_live_enable=explicit,
            ack_live_risks=ack,
            canary_mode=canary,
            safe_mode_default=safe,
            rollout_stage_override=os.getenv("ROBOT_ROLLOUT_STAGE_OVERRIDE", "").strip(),
            provider_whitelist=providers,
            execution=ExecutionSettings(mode=exec_mode),
            safety=SafetySettings(
                live_unlock=LiveUnlockSettings(
                    enable_live_trading=explicit,
                    ack_i_understand_risks=ack,
                    allow_full_live_stage=os.getenv("ENABLE_FULL_LIVE_STAGE", "false").lower() == "true",
                )
            ),
            performance_targets=PerformanceTargetSettings(
                monthly_return_pct=_env_float("AUTONOMOUS_TARGET_MONTHLY_RETURN_PCT", 30.0),
                max_monthly_drawdown_pct=_env_float("AUTONOMOUS_TARGET_MAX_MONTHLY_DRAWDOWN_PCT", 10.0),
                max_intraday_drawdown_pct=_env_float("AUTONOMOUS_TARGET_MAX_INTRADAY_DRAWDOWN_PCT", 3.0),
                round_trips_per_day=_env_float("AUTONOMOUS_TARGET_ROUND_TRIPS_PER_DAY", 1.0),
                capital_utilization_pct=_env_float("AUTONOMOUS_TARGET_CAPITAL_UTILIZATION_PCT", 50.0),
                net_bps_per_trade=_env_float("AUTONOMOUS_TARGET_NET_BPS_PER_TRADE", 20.0),
                expectancy_bps_floor=_env_float("AUTONOMOUS_TARGET_EXPECTANCY_BPS_FLOOR", 5.0),
                fill_rate=_env_float("AUTONOMOUS_TARGET_FILL_RATE", 0.35),
                maker_ratio=_env_float("AUTONOMOUS_TARGET_MAKER_RATIO", 0.70),
                max_inventory_age_minutes=_env_float("AUTONOMOUS_TARGET_MAX_INVENTORY_AGE_MINUTES", 720.0),
            ),
            capital_envelope=CapitalEnvelopeSettings(
                max_pair_exposure_notional=_env_float("AUTONOMOUS_MAX_PAIR_EXPOSURE_NOTIONAL", 250.0),
                reserve_fraction=_env_float("AUTONOMOUS_RESERVE_FRACTION", 0.35),
                max_portfolio_heat=_env_float("AUTONOMOUS_MAX_PORTFOLIO_HEAT", 0.65),
                max_regime_heat=_env_float("AUTONOMOUS_MAX_REGIME_HEAT", 0.45),
                max_playbook_heat=_env_float("AUTONOMOUS_MAX_PLAYBOOK_HEAT", 0.30),
                idle_capital_alert_threshold=_env_float("AUTONOMOUS_IDLE_CAPITAL_ALERT_THRESHOLD", 0.60),
                target_capital_utilization_min=_env_float("AUTONOMOUS_TARGET_CAPITAL_UTILIZATION_MIN", 0.35),
                max_capital_lock_time_min=_env_float("AUTONOMOUS_MAX_CAPITAL_LOCK_TIME_MIN", 720.0),
                capital_efficiency_min_score=_env_float("AUTONOMOUS_CAPITAL_EFFICIENCY_MIN_SCORE", 0.40),
            ),
            market_universe=MarketUniverseSettings(
                pair_universe=_env_csv("AUTONOMOUS_PAIR_UNIVERSE"),
                max_active_pairs=_env_int("AUTONOMOUS_MAX_ACTIVE_PAIRS", 1),
                pair_rotation_interval_s=_env_int("AUTONOMOUS_PAIR_ROTATION_INTERVAL_S", 300),
                pair_min_depth_notional=_env_float("AUTONOMOUS_PAIR_MIN_DEPTH_NOTIONAL", 25000.0),
                pair_max_spread_bps=_env_float("AUTONOMOUS_PAIR_MAX_SPREAD_BPS", 35.0),
                pair_min_expectancy_bps=_env_float("AUTONOMOUS_PAIR_MIN_EXPECTANCY_BPS", 0.0),
                pair_min_fill_rate=_env_float("AUTONOMOUS_PAIR_MIN_FILL_RATE", 0.0),
                pair_clustering_enabled=_env_bool("AUTONOMOUS_PAIR_CLUSTERING_ENABLED", True),
                pair_admission_lookback_trades=_env_int("AUTONOMOUS_PAIR_ADMISSION_LOOKBACK_TRADES", 10),
                pair_expulsion_expectancy_floor_bps=_env_float("AUTONOMOUS_PAIR_EXPULSION_EXPECTANCY_FLOOR_BPS", -10.0),
            ),
        )

    @classmethod
    def from_file(cls, path: str) -> "RobotSettings":
        data = _load_yaml_like(path)
        execution_data = data.get("execution", {})
        safety_data = data.get("safety", {})
        live_unlock_data = safety_data.get("live_unlock", {})
        env_enable_live = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
        env_ack_live = os.getenv("ACK_I_UNDERSTAND_RISKS", "false").lower() == "true"
        env_canary_mode = os.getenv("CANARY_MODE", "false").lower() == "true"
        env_full_live_stage = os.getenv("ENABLE_FULL_LIVE_STAGE", "false").lower() == "true"
        env_event_feed_path = os.getenv("KRAKEN_SPOT_EVENT_FEED_PATH", "").strip()
        env_lifecycle_proof = os.getenv("KRAKEN_SPOT_LIFECYCLE_PROOF_ENABLED", "").strip().lower()
        env_lifecycle_proof_max_notional = os.getenv("KRAKEN_SPOT_LIFECYCLE_PROOF_MAX_NOTIONAL", "").strip()
        env_lifecycle_proof_timeout_s = os.getenv("KRAKEN_SPOT_LIFECYCLE_PROOF_TIMEOUT_S", "").strip()
        env_lifecycle_proof_min_reserve_pct = os.getenv("KRAKEN_SPOT_LIFECYCLE_PROOF_MIN_FREE_QUOTE_RESERVE_PCT", "").strip()
        requested_mode = str(execution_data.get("mode", data.get("mode", "paper")))
        requested_provider = str(execution_data.get("provider_id", "binance_um_perps"))

        if requested_mode in {ExecutionMode.LIVE.value, ExecutionMode.LIVE_TESTNET.value} and requested_provider != "kraken_spot":
            raise ValueError("Live trading blocked: unsupported_doctrine_target_use_kraken_spot")

        # Backward compatible with old top-level flags.
        if "enable_live_trading" in data and "enable_live_trading" not in live_unlock_data:
            live_unlock_data["enable_live_trading"] = bool(data.get("enable_live_trading"))
        if "ack_i_understand_risks" in data and "ack_i_understand_risks" not in live_unlock_data:
            live_unlock_data["ack_i_understand_risks"] = bool(data.get("ack_i_understand_risks"))
        if env_full_live_stage:
            live_unlock_data["allow_full_live_stage"] = True

        kraken_spot_data = dict(execution_data.get("kraken_spot", {}))
        if env_event_feed_path:
            kraken_spot_data["event_feed_path"] = env_event_feed_path
        if env_lifecycle_proof in {"true", "false"}:
            kraken_spot_data["lifecycle_proof_enabled"] = env_lifecycle_proof == "true"
        if env_lifecycle_proof_max_notional:
            kraken_spot_data["lifecycle_proof_max_notional"] = float(env_lifecycle_proof_max_notional)
        if env_lifecycle_proof_timeout_s:
            kraken_spot_data["lifecycle_proof_timeout_s"] = int(env_lifecycle_proof_timeout_s)
        if env_lifecycle_proof_min_reserve_pct:
            kraken_spot_data["lifecycle_proof_min_free_quote_reserve_pct"] = float(env_lifecycle_proof_min_reserve_pct)

        return cls(
            trading_mode=TradingMode(data.get("mode", "paper")),
            explicit_live_enable=bool(data.get("enable_live_trading", False)) or env_enable_live,
            ack_live_risks=bool(data.get("ack_i_understand_risks", False)) or env_ack_live,
            canary_mode=bool(data.get("canary_mode", False)) or env_canary_mode,
            safe_mode_default=bool(data.get("safe_mode_default", True)),
            rollout_stage_override=str(data.get("rollout_stage", os.getenv("ROBOT_ROLLOUT_STAGE_OVERRIDE", "") or "") or "").strip(),
            provider_whitelist=list(data.get("provider_whitelist", [])),
            universe=list(data.get("universe", ["BTCUSDT"])),
            timeframe=data.get("timeframe", "1h"),
            risk=RiskLimits(**data.get("risk", {})),
            execution=ExecutionSettings(
                mode=execution_data.get("mode", data.get("mode", "paper")),
                provider_id=execution_data.get("provider_id", "binance_um_perps"),
                fee_bps=execution_data.get("fee_bps", 2.0),
                slippage_bps=execution_data.get("slippage_bps", 1.0),
                partial_fill_ratio=execution_data.get("partial_fill_ratio", 0.7),
                maker_preference=execution_data.get("maker_preference", True),
                maker_timeout_s=execution_data.get("maker_timeout_s", 30),
                max_participation_rate=execution_data.get("max_participation_rate", 0.1),
                max_pct_volume=execution_data.get("max_pct_volume", 0.1),
                max_pct_top_depth=execution_data.get("max_pct_top_depth", 0.12),
                max_child_orders=execution_data.get("max_child_orders", 5),
                slicing_parts=execution_data.get("slicing_parts", 2),
                binance=BinanceExecutionSettings(**execution_data.get("binance", {})),
                kraken=KrakenExecutionSettings(**execution_data.get("kraken", {})),
                kraken_spot=KrakenSpotExecutionSettings(**kraken_spot_data),
            ),
            safety=SafetySettings(live_unlock=LiveUnlockSettings(**live_unlock_data)),
            policy=PolicySettings(**data.get("policy", {})),
            doctrine=DoctrineSettings(**data.get("doctrine", {})),
            harmony=HarmonySettings(**data.get("harmony", {})),
            market_watch=MarketWatchSettings(**data.get("market_watch", {})),
            tco=TCOSettings(**data.get("tco", {})),
            regime=RegimeSettings(**data.get("regime", {})),
            allocator=AllocatorSettings(**data.get("allocator", {})),
            monitoring=MonitoringSettings(**data.get("monitoring", {})),
            storage=StorageSettings(**data.get("storage", {})),
            fixtures=FixtureSettings(**data.get("fixtures", {})),
            replay=ReplaySettings(**data.get("replay", {})),
            kraken_spot_non_live=KrakenSpotNonLiveSettings(**data.get("kraken_spot_non_live", {})),
            mlops=MLOpsSettings(**data.get("mlops", {})),
            performance_targets=PerformanceTargetSettings(
                **_apply_env_overrides(
                    data.get("performance_targets", {}),
                    {
                        "monthly_return_pct": _env_float("AUTONOMOUS_TARGET_MONTHLY_RETURN_PCT"),
                        "max_monthly_drawdown_pct": _env_float("AUTONOMOUS_TARGET_MAX_MONTHLY_DRAWDOWN_PCT"),
                        "max_intraday_drawdown_pct": _env_float("AUTONOMOUS_TARGET_MAX_INTRADAY_DRAWDOWN_PCT"),
                        "round_trips_per_day": _env_float("AUTONOMOUS_TARGET_ROUND_TRIPS_PER_DAY"),
                        "capital_utilization_pct": _env_float("AUTONOMOUS_TARGET_CAPITAL_UTILIZATION_PCT"),
                        "net_bps_per_trade": _env_float("AUTONOMOUS_TARGET_NET_BPS_PER_TRADE"),
                        "expectancy_bps_floor": _env_float("AUTONOMOUS_TARGET_EXPECTANCY_BPS_FLOOR"),
                        "fill_rate": _env_float("AUTONOMOUS_TARGET_FILL_RATE"),
                        "maker_ratio": _env_float("AUTONOMOUS_TARGET_MAKER_RATIO"),
                        "max_inventory_age_minutes": _env_float("AUTONOMOUS_TARGET_MAX_INVENTORY_AGE_MINUTES"),
                    },
                )
            ),
            capital_envelope=CapitalEnvelopeSettings(
                **_apply_env_overrides(
                    data.get("capital_envelope", {}),
                    {
                        "max_pair_exposure_notional": _env_float("AUTONOMOUS_MAX_PAIR_EXPOSURE_NOTIONAL"),
                        "reserve_fraction": _env_float("AUTONOMOUS_RESERVE_FRACTION"),
                        "max_portfolio_heat": _env_float("AUTONOMOUS_MAX_PORTFOLIO_HEAT"),
                        "max_regime_heat": _env_float("AUTONOMOUS_MAX_REGIME_HEAT"),
                        "max_playbook_heat": _env_float("AUTONOMOUS_MAX_PLAYBOOK_HEAT"),
                        "idle_capital_alert_threshold": _env_float("AUTONOMOUS_IDLE_CAPITAL_ALERT_THRESHOLD"),
                        "target_capital_utilization_min": _env_float("AUTONOMOUS_TARGET_CAPITAL_UTILIZATION_MIN"),
                        "max_capital_lock_time_min": _env_float("AUTONOMOUS_MAX_CAPITAL_LOCK_TIME_MIN"),
                        "capital_efficiency_min_score": _env_float("AUTONOMOUS_CAPITAL_EFFICIENCY_MIN_SCORE"),
                    },
                )
            ),
            market_universe=MarketUniverseSettings(
                **_apply_env_overrides(
                    data.get("market_universe", {}),
                    {
                        "pair_universe": _env_csv("AUTONOMOUS_PAIR_UNIVERSE") or None,
                        "max_active_pairs": _env_int("AUTONOMOUS_MAX_ACTIVE_PAIRS"),
                        "pair_rotation_interval_s": _env_int("AUTONOMOUS_PAIR_ROTATION_INTERVAL_S"),
                        "pair_min_depth_notional": _env_float("AUTONOMOUS_PAIR_MIN_DEPTH_NOTIONAL"),
                        "pair_max_spread_bps": _env_float("AUTONOMOUS_PAIR_MAX_SPREAD_BPS"),
                        "pair_min_expectancy_bps": _env_float("AUTONOMOUS_PAIR_MIN_EXPECTANCY_BPS"),
                        "pair_min_fill_rate": _env_float("AUTONOMOUS_PAIR_MIN_FILL_RATE"),
                        "pair_clustering_enabled": _env_bool("AUTONOMOUS_PAIR_CLUSTERING_ENABLED"),
                        "pair_admission_lookback_trades": _env_int("AUTONOMOUS_PAIR_ADMISSION_LOOKBACK_TRADES"),
                        "pair_expulsion_expectancy_floor_bps": _env_float("AUTONOMOUS_PAIR_EXPULSION_EXPECTANCY_FLOOR_BPS"),
                    },
                )
            ),
            playbooks=PlaybookSettings(**data.get("playbooks", {})),
            expectancy=ExpectancySettings(**data.get("expectancy", {})),
            experiments=ExperimentsSettings(**data.get("experiments", {})),
            operator_kpis=OperatorKPISettings(**data.get("operator_kpis", {})),
            margin=MarginSettings(**data.get("margin", {})),
        )

    def __post_init__(self) -> None:
        if isinstance(self.trading_mode, str):
            self.trading_mode = TradingMode(self.trading_mode)
        self._validate()

    def execution_mode_enum(self) -> ExecutionMode:
        # Legacy configs used top-level mode=live without execution.mode.
        if self.execution.mode == "paper" and self.trading_mode == TradingMode.LIVE:
            return ExecutionMode.LIVE
        return ExecutionMode(self.execution.mode)

    def live_ordering_enabled(self) -> bool:
        mode = self.execution_mode_enum()
        return mode in {ExecutionMode.LIVE, ExecutionMode.LIVE_TESTNET}

    def doctrine_target_provider(self) -> str:
        return self.doctrine.target_provider or self.execution.provider_id

    def doctrine_product_target(self) -> str:
        provider_id = self.doctrine_target_provider()
        return self.doctrine.product_target or ("spot" if provider_id.endswith("_spot") else "perps")

    def kraken_spot_doctrine_active(self) -> bool:
        return bool(
            self.doctrine_target_provider() == "kraken_spot"
            and self.doctrine_product_target() == "spot"
            and self.doctrine.long_only
            and self.doctrine.never_open_new_short_exposure
        )

    def kraken_spot_non_live_profile(self) -> str:
        return str(self.kraken_spot_non_live.profile or "legacy")

    def kraken_spot_full_analysis_enabled(self) -> bool:
        return bool(
            self.execution.provider_id == "kraken_spot"
            and self.execution_mode_enum() in {ExecutionMode.PAPER, ExecutionMode.LIVE_READONLY}
            and self.kraken_spot_doctrine_active()
            and self.kraken_spot_non_live_profile() == "full_analysis"
        )

    def full_live_stage_enabled(self) -> bool:
        return bool(self.safety.live_unlock.allow_full_live_stage)

    def kraken_spot_event_feed_path(self) -> str:
        return str(self.execution.kraken_spot.event_feed_path or "")

    def kraken_spot_lifecycle_proof(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.execution.kraken_spot.lifecycle_proof_enabled),
            "max_notional": float(self.execution.kraken_spot.lifecycle_proof_max_notional),
            "timeout_s": int(self.execution.kraken_spot.lifecycle_proof_timeout_s),
            "min_free_quote_reserve_pct": None
            if self.execution.kraken_spot.lifecycle_proof_min_free_quote_reserve_pct is None
            else float(self.execution.kraken_spot.lifecycle_proof_min_free_quote_reserve_pct),
        }

    def rollout_stage_configured(self) -> RolloutStage | None:
        raw = str(self.rollout_stage_override or "").strip()
        if not raw:
            return None
        return RolloutStage(raw)

    def rollout_stage(self) -> RolloutStage:
        mode = self.execution_mode_enum()
        configured = self.rollout_stage_configured()
        if configured is not None:
            return configured
        if mode == ExecutionMode.PAPER:
            return RolloutStage.PAPER
        if mode == ExecutionMode.LIVE_READONLY:
            return RolloutStage.SHADOW
        if mode == ExecutionMode.LIVE_TESTNET:
            return RolloutStage.TINY_LIVE
        run_dir = self.storage.run_dir.lower()
        if self.canary_mode or "canary" in run_dir:
            return RolloutStage.CANARY_LIVE
        if float(self.policy.base_risk_budget) <= 100.0:
            return RolloutStage.LIMITED_LIVE
        return RolloutStage.NORMAL_LIVE

    def rollout_profile(self) -> dict[str, Any]:
        stage = self.rollout_stage()
        mode = self.execution_mode_enum()
        base = {
            "resolved_stage": stage.value,
            "runtime_mode": mode.value,
            "base_risk_budget": float(self.policy.base_risk_budget),
            "max_position_notional": float(self.risk.max_position_notional if self.risk.max_position_notional != UNSPECIFIED else 0.0),
            "max_exposure_notional": float(self.risk.max_exposure_notional if self.risk.max_exposure_notional != UNSPECIFIED else 0.0),
            "max_orders_per_min": int(self.risk.max_orders_per_min if self.risk.max_orders_per_min != UNSPECIFIED else 0),
            "max_spread_bps": float(self.risk.max_spread_bps if self.risk.max_spread_bps != UNSPECIFIED else 0.0),
            "min_depth_notional": float(self.risk.min_depth_notional if self.risk.min_depth_notional != UNSPECIFIED else 0.0),
            "safe_mode_default": bool(self.safe_mode_default),
            "canary_mode": bool(self.canary_mode),
            "full_live_stage_enabled": self.full_live_stage_enabled(),
        }
        profiles: dict[RolloutStage, dict[str, Any]] = {
            RolloutStage.PAPER: {
                "purpose": "simulation_only",
                "allowed_actions": ["paper_trade", "journal", "report"],
                "blocked_actions": ["live_order_submission"],
                "aggression_envelope": "simulation",
                "downgrade_triggers": ["paper_truth_gap"],
                "promotion_prerequisites": ["paper_replay_green"],
                "rollback_target": "paper",
            },
            RolloutStage.SHADOW: {
                "purpose": "live_data_full_analytics_no_execution",
                "allowed_actions": ["live_data_ingestion", "decisioning", "analytics", "report"],
                "blocked_actions": ["live_order_submission"],
                "aggression_envelope": "no_opening_allowed",
                "downgrade_triggers": ["market_integrity_degrade", "truth_confidence_gap"],
                "promotion_prerequisites": ["preflight_ok", "operator_summary_visible", "market_watch_active"],
                "rollback_target": "paper",
            },
            RolloutStage.TINY_LIVE: {
                "purpose": "first_real_money_truth_and_execution_validation",
                "allowed_actions": ["buy_entries", "reduce_only_sells", "flatten", "freeze_new_open"],
                "blocked_actions": ["full_stage_sizing", "doctrine_incompatible_paths"],
                "aggression_envelope": "tiny_size_probe_only",
                "downgrade_triggers": ["truth_degrade", "reconciliation_gap", "market_watch_block", "market_integrity_degrade"],
                "promotion_prerequisites": ["manual_promotion", "tiny_live_readiness_report.ready", "rollback_preflight_ready"],
                "rollback_target": "shadow",
            },
            RolloutStage.CANARY_LIVE: {
                "purpose": "legacy_canary_live_probe",
                "allowed_actions": ["buy_entries", "reduce_only_sells", "flatten", "freeze_new_open"],
                "blocked_actions": ["full_stage_sizing", "doctrine_incompatible_paths"],
                "aggression_envelope": "small_probe_only",
                "downgrade_triggers": ["truth_degrade", "reconciliation_gap", "market_watch_block", "market_integrity_degrade"],
                "promotion_prerequisites": ["manual_promotion", "canary_metrics_clean"],
                "rollback_target": "shadow",
            },
            RolloutStage.LIMITED_LIVE: {
                "purpose": "restricted_real_money_live",
                "allowed_actions": ["buy_entries", "reduce_only_sells", "flatten", "freeze_new_open"],
                "blocked_actions": ["full_stage_sizing"],
                "aggression_envelope": "reduced_size",
                "downgrade_triggers": ["truth_degrade", "market_watch_degrade", "execution_health_bad"],
                "promotion_prerequisites": ["manual_promotion", "tiny_live_passed"],
                "rollback_target": "tiny_live",
            },
            RolloutStage.NORMAL_LIVE: {
                "purpose": "full_doctrine_live_with_hard_guards",
                "allowed_actions": ["buy_entries", "reduce_only_sells", "flatten", "freeze_new_open"],
                "blocked_actions": ["short_opening", "unsafe_sell_paths"],
                "aggression_envelope": "full_safe_autonomy",
                "downgrade_triggers": ["truth_degrade", "market_watch_degrade", "reconciliation_gap", "market_integrity_degrade"],
                "promotion_prerequisites": ["manual_promotion", "ENABLE_FULL_LIVE_STAGE"],
                "rollback_target": "limited_live",
            },
        }
        return {**base, **profiles.get(stage, profiles[RolloutStage.LIMITED_LIVE])}

    def live_gate_status(self) -> dict[str, Any]:
        unlock = self.safety.live_unlock
        env_enable_live = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
        env_ack_live = os.getenv("ACK_I_UNDERSTAND_RISKS", "false").lower() == "true"
        provider_id = self.execution.provider_id
        doctrine_provider = self.doctrine_target_provider()
        doctrine_product = self.doctrine_product_target()
        enable_live = bool(unlock.enable_live_trading or self.explicit_live_enable)
        ack_live = bool(unlock.ack_i_understand_risks or self.ack_live_risks)
        full_live_stage = bool(unlock.allow_full_live_stage)
        resolved_stage = self.rollout_stage()
        doctrine_launch_safe = bool(
            doctrine_provider == "kraken_spot"
            and doctrine_product == "spot"
            and self.doctrine.long_only
            and self.doctrine.never_open_new_short_exposure
            and self.doctrine.enforce_cost_basis_sell_block
            and self.doctrine.enforce_net_profit_sell_block
            and self.doctrine.block_non_reduce_only_sells
            and float(self.doctrine.minimum_sell_net_profit_bps) >= 120.0
            and bool(self.harmony.enabled)
            and bool(self.market_watch.enabled)
        )
        return {
            "rollout_stage": self.rollout_stage().value,
            "runtime_mode": self.execution_mode_enum().value,
            "provider_id": provider_id,
            "provider_supported": provider_id in SUPPORTED_PROVIDER_IDS,
            "provider_whitelisted": provider_id in self.provider_whitelist,
            "live_ordering_enabled": self.live_ordering_enabled(),
            "double_unlock_enabled": enable_live and ack_live,
            "unlock_live_requested": enable_live,
            "unlock_acknowledged": ack_live,
            "unlock_sources": {
                "settings_enable_live_trading": bool(unlock.enable_live_trading),
                "settings_ack_i_understand_risks": bool(unlock.ack_i_understand_risks),
                "legacy_top_level_enable_live_trading": bool(self.explicit_live_enable and not env_enable_live),
                "legacy_top_level_ack_i_understand_risks": bool(self.ack_live_risks and not env_ack_live),
                "env_enable_live_trading": env_enable_live,
                "env_ack_i_understand_risks": env_ack_live,
            },
            "full_live_stage_enabled": full_live_stage,
            "full_live_stage_required": bool(
                self.execution_mode_enum() == ExecutionMode.LIVE
                and unlock.canary_required_before_full
                and resolved_stage == RolloutStage.NORMAL_LIVE
            ),
            "full_live_stage_sources": {
                "settings_allow_full_live_stage": bool(unlock.allow_full_live_stage and os.getenv("ENABLE_FULL_LIVE_STAGE", "").lower() != "true"),
                "env_allow_full_live_stage": os.getenv("ENABLE_FULL_LIVE_STAGE", "false").lower() == "true",
            },
            "margin_enabled": self.margin.enabled,
            "canary_mode": self.canary_mode,
            "doctrine_target_provider": doctrine_provider,
            "doctrine_product_target": doctrine_product,
            "long_only": bool(self.doctrine.long_only),
            "cost_basis_sell_block": bool(self.doctrine.enforce_cost_basis_sell_block),
            "net_profit_sell_block": bool(self.doctrine.enforce_net_profit_sell_block),
            "harmony_enabled": bool(self.harmony.enabled),
            "market_watch_enabled": bool(self.market_watch.enabled),
            "event_feed_configured": bool(self.kraken_spot_event_feed_path()),
            "event_feed_path": self.kraken_spot_event_feed_path(),
            "lifecycle_proof": self.kraken_spot_lifecycle_proof(),
            "doctrine_launch_safe": doctrine_launch_safe,
            "rollout_profile": self.rollout_profile(),
        }

    def config_hash(self) -> str:
        payload = json.dumps(self.config_manifest(), sort_keys=True, default=str)
        return sha256(payload.encode("utf-8")).hexdigest()

    def config_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.config_schema_version,
            "runtime_mode": self.execution_mode_enum().value,
            "rollout_stage": self.rollout_stage().value,
            "rollout_stage_override": self.rollout_stage_override,
            "rollout_profile": self.rollout_profile(),
            "provider_id": self.execution.provider_id,
            "universe": list(self.universe),
            "safe_mode_default": self.safe_mode_default,
            "margin_enabled": self.margin.enabled,
            "doctrine": {
                "target_provider": self.doctrine.target_provider,
                "product_target": self.doctrine.product_target,
                "long_only": self.doctrine.long_only,
                "never_open_new_short_exposure": self.doctrine.never_open_new_short_exposure,
                "minimum_sell_net_profit_bps": self.doctrine.minimum_sell_net_profit_bps,
                "enforce_cost_basis_sell_block": self.doctrine.enforce_cost_basis_sell_block,
                "enforce_net_profit_sell_block": self.doctrine.enforce_net_profit_sell_block,
                "block_non_reduce_only_sells": self.doctrine.block_non_reduce_only_sells,
            },
            "harmony": {
                "enabled": self.harmony.enabled,
                "default_order_cadence_s": self.harmony.default_order_cadence_s,
            },
            "market_watch": {
                "enabled": self.market_watch.enabled,
                "blackout_windows": list(self.market_watch.blackout_windows),
                "entry_block_max_spread_bps": self.market_watch.entry_block_max_spread_bps,
                "entry_degrade_max_spread_bps": self.market_watch.entry_degrade_max_spread_bps,
                "entry_block_min_depth_notional": self.market_watch.entry_block_min_depth_notional,
                "entry_degrade_min_depth_notional": self.market_watch.entry_degrade_min_depth_notional,
                "liquidity_map_min_depth_notional": self.market_watch.liquidity_map_min_depth_notional,
                "block_new_entries_on_blackout": self.market_watch.block_new_entries_on_blackout,
            },
            "kraken_spot_non_live": {
                "profile": self.kraken_spot_non_live.profile,
                "event_fixture_path": self.kraken_spot_non_live.event_fixture_path,
                "event_recording_path": self.kraken_spot_non_live.event_recording_path,
                "emit_operator_bundle": self.kraken_spot_non_live.emit_operator_bundle,
                "emit_replay_bundle": self.kraken_spot_non_live.emit_replay_bundle,
                "full_analysis_enabled": self.kraken_spot_full_analysis_enabled(),
            },
            "kraken_spot_live": {
                "event_feed_path": self.kraken_spot_event_feed_path(),
                "full_live_stage_enabled": self.full_live_stage_enabled(),
                "lifecycle_proof": self.kraken_spot_lifecycle_proof(),
            },
            "live_gate_status": self.live_gate_status(),
            "monitoring": {
                "decision_latency_warn_ms": self.monitoring.decision_latency_warn_ms,
                "reconciliation_lag_warn_ms": self.monitoring.reconciliation_lag_warn_ms,
                "loop_latency_warn_ms": self.monitoring.loop_latency_warn_ms,
                "manual_review_ack_ttl_minutes": self.monitoring.manual_review_ack_ttl_minutes,
            },
            "performance_targets": {
                "monthly_return_pct": self.performance_targets.monthly_return_pct,
                "max_monthly_drawdown_pct": self.performance_targets.max_monthly_drawdown_pct,
                "max_intraday_drawdown_pct": self.performance_targets.max_intraday_drawdown_pct,
                "round_trips_per_day": self.performance_targets.round_trips_per_day,
                "capital_utilization_pct": self.performance_targets.capital_utilization_pct,
                "net_bps_per_trade": self.performance_targets.net_bps_per_trade,
                "expectancy_bps_floor": self.performance_targets.expectancy_bps_floor,
                "fill_rate": self.performance_targets.fill_rate,
                "maker_ratio": self.performance_targets.maker_ratio,
                "max_inventory_age_minutes": self.performance_targets.max_inventory_age_minutes,
            },
            "capital_envelope": {
                "max_pair_exposure_notional": self.capital_envelope.max_pair_exposure_notional,
                "reserve_fraction": self.capital_envelope.reserve_fraction,
                "max_portfolio_heat": self.capital_envelope.max_portfolio_heat,
                "max_regime_heat": self.capital_envelope.max_regime_heat,
                "max_playbook_heat": self.capital_envelope.max_playbook_heat,
                "idle_capital_alert_threshold": self.capital_envelope.idle_capital_alert_threshold,
                "target_capital_utilization_min": self.capital_envelope.target_capital_utilization_min,
                "max_capital_lock_time_min": self.capital_envelope.max_capital_lock_time_min,
                "capital_efficiency_min_score": self.capital_envelope.capital_efficiency_min_score,
            },
            "market_universe": {
                "pair_universe": list(self.market_universe.pair_universe),
                "max_active_pairs": self.market_universe.max_active_pairs,
                "pair_rotation_interval_s": self.market_universe.pair_rotation_interval_s,
                "pair_min_depth_notional": self.market_universe.pair_min_depth_notional,
                "pair_max_spread_bps": self.market_universe.pair_max_spread_bps,
                "pair_min_expectancy_bps": self.market_universe.pair_min_expectancy_bps,
                "pair_min_fill_rate": self.market_universe.pair_min_fill_rate,
                "pair_clustering_enabled": self.market_universe.pair_clustering_enabled,
                "pair_admission_lookback_trades": self.market_universe.pair_admission_lookback_trades,
                "pair_expulsion_expectancy_floor_bps": self.market_universe.pair_expulsion_expectancy_floor_bps,
            },
            "playbooks": {
                "enable_multi_playbook_shadow": self.playbooks.enable_multi_playbook_shadow,
                "enable_multi_pair_shadow": self.playbooks.enable_multi_pair_shadow,
                "live_candidate_auction_enabled": self.playbooks.live_candidate_auction_enabled,
                "max_backlog_candidates": self.playbooks.max_backlog_candidates,
                "default_opportunity_half_life_s": self.playbooks.default_opportunity_half_life_s,
                "signal_crowding_limit": self.playbooks.signal_crowding_limit,
                "shadow_only_playbooks": list(self.playbooks.shadow_only_playbooks),
            },
            "expectancy": {
                "rolling_window_trades": self.expectancy.rolling_window_trades,
                "min_sample_guard": self.expectancy.min_sample_guard,
                "size_down_expectancy_floor_bps": self.expectancy.size_down_expectancy_floor_bps,
                "cooldown_expectancy_floor_bps": self.expectancy.cooldown_expectancy_floor_bps,
                "disable_expectancy_floor_bps": self.expectancy.disable_expectancy_floor_bps,
                "promotion_expectancy_bps": self.expectancy.promotion_expectancy_bps,
                "intraday_session_buckets": list(self.expectancy.intraday_session_buckets),
            },
            "experiments": {
                "enabled": self.experiments.enabled,
                "evidence_min_trades": self.experiments.evidence_min_trades,
                "rollback_loss_bps": self.experiments.rollback_loss_bps,
                "staged_variants_enabled": self.experiments.staged_variants_enabled,
                "shadow_variant_bias": self.experiments.shadow_variant_bias,
                "promotion_score_min": self.experiments.promotion_score_min,
            },
            "operator_kpis": {
                "expose_advanced_runtime_panels": self.operator_kpis.expose_advanced_runtime_panels,
                "backlog_pressure_warn": self.operator_kpis.backlog_pressure_warn,
                "capital_efficiency_warn": self.operator_kpis.capital_efficiency_warn,
                "live_degradation_warn": self.operator_kpis.live_degradation_warn,
                "false_negative_warn": self.operator_kpis.false_negative_warn,
                "false_positive_warn": self.operator_kpis.false_positive_warn,
            },
        }

    def _critical_risk_limits(self) -> list[float | int | str]:
        return [
            self.risk.max_daily_loss_pct,
            self.risk.max_drawdown_pct,
            self.risk.max_position_notional,
            self.risk.max_exposure_notional,
            self.risk.max_orders_per_min,
            self.risk.leverage,
            self.risk.max_spread_bps,
            self.risk.min_depth_notional,
            self.risk.stale_data_seconds,
            self.risk.min_margin_buffer,
            self.risk.max_funding_cost_per_day,
            self.risk.max_oi_spike_pct,
            self.risk.max_liquidation_spike,
            self.risk.divergence_threshold_bps,
            self.risk.crowding_score_kill,
            self.tco.max_total_cost_bps,
            self.tco.max_impact_bps,
        ]

    def _validate(self) -> None:
        mode = self.execution_mode_enum()
        unlock = self.safety.live_unlock

        if self.margin.enabled and mode != ExecutionMode.PAPER:
            raise ValueError("Margin live trading blocked until dedicated safety layer is implemented")

        if mode == ExecutionMode.PAPER:
            return

        # Global live connector guard for non-paper execution modes.
        provider_id = self.execution.provider_id
        if provider_id not in SUPPORTED_PROVIDER_IDS:
            raise ValueError(f"Unsupported execution provider: {provider_id}")
        if provider_id not in self.provider_whitelist:
            raise ValueError(f"Live execution blocked: provider_whitelist missing {provider_id}")

        if mode == ExecutionMode.LIVE_READONLY:
            return

        if mode == ExecutionMode.LIVE and provider_id != "kraken_spot":
            raise ValueError("Live trading blocked: unsupported_doctrine_target_use_kraken_spot")

        missing = []
        enable_live = unlock.enable_live_trading or self.explicit_live_enable
        ack_live = unlock.ack_i_understand_risks or self.ack_live_risks

        if not enable_live:
            missing.append("ENABLE_LIVE_TRADING")
        if not ack_live:
            missing.append("ACK_I_UNDERSTAND_RISKS")
        if any(v == UNSPECIFIED for v in self._critical_risk_limits()):
            missing.append("critical risk limits")

        if provider_id == "kraken_derivatives":
            api_key_env = self.execution.kraken.api_key_env
            api_secret_env = self.execution.kraken.api_secret_env
        elif provider_id == "kraken_spot":
            api_key_env = self.execution.kraken_spot.api_key_env
            api_secret_env = self.execution.kraken_spot.api_secret_env
        else:
            api_key_env = self.execution.binance.api_key_env
            api_secret_env = self.execution.binance.api_secret_env
        api_key = os.getenv(api_key_env, "")
        api_secret = os.getenv(api_secret_env, "")
        if not api_key or not api_secret:
            missing.append(f"{provider_id}_api_credentials")

        doctrine_guard_required = provider_id == "kraken_spot" or mode == ExecutionMode.LIVE
        if doctrine_guard_required:
            doctrine_provider = self.doctrine_target_provider()
            doctrine_product = self.doctrine_product_target()
            if doctrine_provider != "kraken_spot":
                missing.append("doctrine.target_provider=kraken_spot")
            if doctrine_product != "spot":
                missing.append("doctrine.product_target=spot")
            if not self.doctrine.long_only:
                missing.append("doctrine.long_only")
            if not self.doctrine.never_open_new_short_exposure:
                missing.append("doctrine.never_open_new_short_exposure")
            if not self.doctrine.enforce_cost_basis_sell_block:
                missing.append("doctrine.enforce_cost_basis_sell_block")
            if not self.doctrine.enforce_net_profit_sell_block:
                missing.append("doctrine.enforce_net_profit_sell_block")
            if not self.doctrine.block_non_reduce_only_sells:
                missing.append("doctrine.block_non_reduce_only_sells")
            if float(self.doctrine.minimum_sell_net_profit_bps) < 120.0:
                missing.append("doctrine.minimum_sell_net_profit_bps>=120")
            if not self.harmony.enabled:
                missing.append("harmony.enabled")
            if not self.market_watch.enabled:
                missing.append("market_watch.enabled")

        if mode == ExecutionMode.LIVE and unlock.canary_required_before_full and not self.canary_mode and not unlock.allow_full_live_stage:
            if self.rollout_stage() == RolloutStage.NORMAL_LIVE:
                missing.append("ENABLE_FULL_LIVE_STAGE")
        if mode == ExecutionMode.LIVE and unlock.require_testnet_passed:
            if os.getenv("TESTNET_VALIDATED", "false").lower() != "true":
                missing.append("TESTNET_VALIDATED")

        configured_rollout = self.rollout_stage_configured()
        if configured_rollout is not None:
            if mode == ExecutionMode.PAPER and configured_rollout != RolloutStage.PAPER:
                missing.append("rollout_stage_override_invalid_for_paper")
            if mode == ExecutionMode.LIVE_READONLY and configured_rollout != RolloutStage.SHADOW:
                missing.append("rollout_stage_override_invalid_for_live_readonly")
            if mode == ExecutionMode.LIVE_TESTNET and configured_rollout != RolloutStage.TINY_LIVE:
                missing.append("rollout_stage_override_invalid_for_live_testnet")
            if mode == ExecutionMode.LIVE and configured_rollout in {RolloutStage.PAPER, RolloutStage.SHADOW}:
                missing.append("rollout_stage_override_invalid_for_live")

        if missing:
            raise ValueError(f"Live trading blocked until configured: {missing}")


def _env_bool(name: str, default: bool | None = None) -> bool | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_float(name: str, default: float | None = None) -> float | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _env_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(float(raw))
    except Exception:
        return default


def _env_csv(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _apply_env_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in overrides.items():
        if value is None:
            continue
        merged[key] = value
    return merged


def _load_yaml_like(path: str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        out = yaml.safe_load(text)
        if isinstance(out, dict):
            return out
    except Exception:
        pass
    return json.loads(text)
