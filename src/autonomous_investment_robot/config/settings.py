from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

UNSPECIFIED = "UNSPECIFIED"


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE_READONLY = "live_readonly"
    LIVE_TESTNET = "live_testnet"
    LIVE = "live"


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
class KrakenSpotExecutionSettings:
    rest_base_url: str = "https://api.kraken.com"
    api_key_env: str = "KRAKEN_API_KEY"
    api_secret_env: str = "KRAKEN_API_SECRET"
    request_timeout_s: float = 10.0
    rate_limit_rps: float = 2.0
    max_retries: int = 3
    backoff_base_ms: int = 300
    backoff_max_ms: int = 4000
    allow_unknown_permissions: bool = False
    require_open_orders_scope: bool = False
    dry_run_long_only: bool = True


@dataclass
class UniverseBuilderSettings:
    top_n_target: int = 1000
    refresh_interval_hours: float = 6.0
    candidate_min: int = 100
    candidate_max: int = 200
    trade_max_positions: int = 20
    min_24h_quote_volume: float = 100000.0
    max_spread_bps: float = 25.0
    min_depth_notional: float = 0.0


@dataclass
class ExecutionSettings:
    mode: str = "paper"
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
    kraken_spot: KrakenSpotExecutionSettings = field(default_factory=KrakenSpotExecutionSettings)


@dataclass
class LiveUnlockSettings:
    enable_live_trading: bool = False
    ack_i_understand_risks: bool = False
    require_testnet_passed: bool = True
    canary_required_before_full: bool = True
    require_operator_confirmation_artifact: bool = True
    operator_confirmation_file: str = "ops/live_operator_confirmation.txt"


@dataclass
class SafetySettings:
    live_unlock: LiveUnlockSettings = field(default_factory=LiveUnlockSettings)


@dataclass
class PolicySettings:
    confidence_threshold: float = 0.55
    estimated_cost_bps: float = 3.0
    safety_buffer_bps: float = 1.0
    base_risk_budget: float = 1000.0


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


@dataclass
class MarketCoverageSettings:
    enable_spot: bool = True
    enable_margin: bool = True
    enable_perps: bool = True
    enable_optional_venues: bool = True
    discover_all_symbols: bool = True
    max_symbols: int = 0
    enable_crypto_spot: bool = True
    enable_xstocks: bool = False
    enable_xstocks_etf: bool = False
    xstocks_allowlist: list[str] = field(default_factory=list)
    xstocks_denylist: list[str] = field(default_factory=list)
    mixed_universe_mode: bool = False


@dataclass
class WatchdogSettings:
    enabled: bool = True
    poll_interval_s: float = 2.0
    stall_timeout_s: float = 45.0
    restart_backoff_s: float = 5.0
    max_restarts: int = 0
    heartbeat_file: str = "health.json"
    state_file: str = "watchdog_state.json"


@dataclass
class HealthAudit110Settings:
    enabled: bool = True
    interval_s: float = 600.0
    health_threshold: float = 90.0
    stream_stale_after_s: float = 20.0
    scheduler_lag_grace_s: float = 5.0
    max_rate_limit_events_60s: float = 14.0
    pause_openings_s: float = 180.0


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
class MLOpsSettings:
    retrain_enabled: bool = True
    canary_risk_pct: float = 0.05
    rollback_dd_threshold_pct: float = 2.0
    drift_psi_threshold: float = 0.2


@dataclass
class LLMSettings:
    provider: str = "auto"
    model: str = ""
    model_primary: str = ""
    model_fallback: str = ""
    base_url: str = ""
    enabled: bool = True
    timeout_s: float = 12.0
    max_retries: int = 1
    healthcheck_remote: bool = False
    self_improvement_enabled: bool = True
    self_improvement_hours: float = 24.0
    self_improvement_every_s: float = 1800.0
    llm_augment_enabled: bool = False


@dataclass
class DistributedRuntimeSettings:
    enabled: bool = False
    node_role: str = "live"
    compute_bridge: str = "auto"
    compute_timeout_s: float = 0.8
    compute_refresh_s: float = 10.0
    compute_top_n: int = 24
    redis_url: str = ""
    stream_prefix: str = "autobot"
    stream_payload_version: str = "v1"
    allow_local_fallback: bool = True
    enforce_remote_compute: bool = False
    postgres_mirror_enabled: bool = False
    postgres_dsn: str = ""
    postgres_connect_timeout_s: float = 2.0
    disable_advisory_on_live: bool = True


@dataclass
class AutonomousDecisionSettings:
    confidence_threshold: float = 0.55
    uncertainty_threshold_bps: float = 85.0
    confidence_threshold_crypto: float = 0.52
    confidence_threshold_xstock: float = 0.58
    confidence_threshold_xstock_etf: float = 0.60
    uncertainty_threshold_bps_crypto: float = 92.0
    uncertainty_threshold_bps_xstock: float = 74.0
    uncertainty_threshold_bps_xstock_etf: float = 68.0
    conformal_alpha: float = 0.1
    drift_threshold: float = 0.2
    regime_hold_s: float = 30.0
    max_slippage_guard_bps: float = 8.0
    latency_risk_threshold: float = 0.65
    max_drawdown_guard_pct: float = 8.0
    online_learning_enabled: bool = True
    online_learning_rate: float = 0.02
    enable_news_features: bool = False
    enable_macro_features: bool = False
    enable_fundamental_features: bool = False
    enable_sentiment_features: bool = False
    signal_decay_guard_threshold: float = 0.6
    execution_quality_guard_threshold: float = 2.5
    liquidity_pressure_guard_threshold: float = -0.6
    adaptive_hold_base_s: float = 1800.0
    forecast_backend: str = "baseline"
    forecast_backend_plugin: str = ""
    transformer_backend_enabled: bool = False
    foundation_backend_enabled: bool = False
    self_optimization_window: int = 120
    self_optimization_min_samples: int = 24
    self_optimization_apply_every: int = 12
    regime_size_mult_bull_trend: float = 1.15
    regime_size_mult_trend: float = 1.10
    regime_size_mult_range: float = 0.95
    regime_size_mult_chop: float = 0.80
    regime_size_mult_panic: float = 0.45
    regime_size_mult_high_vol: float = 0.60
    regime_size_mult_low_liquidity: float = 0.55
    opportunity_decay_max_age_s: float = 45.0
    opportunity_decay_guard_threshold: float = 0.65
    cross_market_confirmation_enabled: bool = True
    cross_market_confirmation_min: float = -0.35
    counterfactual_min_edge_bps: float = 1.0
    market_twin_include_advanced_scenarios: bool = True
    market_twin_max_snapshots: int = 256


@dataclass
class RobotSettings:
    trading_mode: TradingMode = TradingMode.PAPER
    explicit_live_enable: bool = False
    ack_live_risks: bool = False
    canary_mode: bool = False
    safe_mode_default: bool = True
    provider_whitelist: list[str] = field(default_factory=list)
    universe: list[str] = field(default_factory=lambda: ["BTCUSDT"])
    timeframe: str = "1h"
    risk: RiskLimits = field(default_factory=RiskLimits)
    execution: ExecutionSettings = field(default_factory=ExecutionSettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    policy: PolicySettings = field(default_factory=PolicySettings)
    tco: TCOSettings = field(default_factory=TCOSettings)
    regime: RegimeSettings = field(default_factory=RegimeSettings)
    allocator: AllocatorSettings = field(default_factory=AllocatorSettings)
    monitoring: MonitoringSettings = field(default_factory=MonitoringSettings)
    market_coverage: MarketCoverageSettings = field(default_factory=MarketCoverageSettings)
    watchdog: WatchdogSettings = field(default_factory=WatchdogSettings)
    health_audit_110: HealthAudit110Settings = field(default_factory=HealthAudit110Settings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    fixtures: FixtureSettings = field(default_factory=FixtureSettings)
    replay: ReplaySettings = field(default_factory=ReplaySettings)
    mlops: MLOpsSettings = field(default_factory=MLOpsSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    distributed: DistributedRuntimeSettings = field(default_factory=DistributedRuntimeSettings)
    universe_builder: UniverseBuilderSettings = field(default_factory=UniverseBuilderSettings)
    autonomous: AutonomousDecisionSettings = field(default_factory=AutonomousDecisionSettings)

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
            provider_whitelist=providers,
            execution=ExecutionSettings(mode=exec_mode),
        )

    @classmethod
    def from_file(cls, path: str) -> "RobotSettings":
        data = _load_yaml_like(path)
        execution_data = data.get("execution", {})
        safety_data = data.get("safety", {})
        live_unlock_data = safety_data.get("live_unlock", {})

        # Backward compatible with old top-level flags.
        if "enable_live_trading" in data and "enable_live_trading" not in live_unlock_data:
            live_unlock_data["enable_live_trading"] = bool(data.get("enable_live_trading"))
        if "ack_i_understand_risks" in data and "ack_i_understand_risks" not in live_unlock_data:
            live_unlock_data["ack_i_understand_risks"] = bool(data.get("ack_i_understand_risks"))

        return cls(
            trading_mode=TradingMode(data.get("mode", "paper")),
            explicit_live_enable=bool(data.get("enable_live_trading", False)),
            ack_live_risks=bool(data.get("ack_i_understand_risks", False)),
            canary_mode=bool(data.get("canary_mode", False)),
            safe_mode_default=bool(data.get("safe_mode_default", True)),
            provider_whitelist=list(data.get("provider_whitelist", [])),
            universe=list(data.get("universe", ["BTCUSDT"])),
            timeframe=data.get("timeframe", "1h"),
            risk=RiskLimits(**data.get("risk", {})),
            execution=ExecutionSettings(
                mode=execution_data.get("mode", data.get("mode", "paper")),
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
                kraken_spot=KrakenSpotExecutionSettings(**execution_data.get("kraken_spot", {})),
            ),
            safety=SafetySettings(live_unlock=LiveUnlockSettings(**live_unlock_data)),
            policy=PolicySettings(**data.get("policy", {})),
            tco=TCOSettings(**data.get("tco", {})),
            regime=RegimeSettings(**data.get("regime", {})),
            allocator=AllocatorSettings(**data.get("allocator", {})),
            monitoring=MonitoringSettings(**data.get("monitoring", {})),
            market_coverage=MarketCoverageSettings(**data.get("market_coverage", {})),
            watchdog=WatchdogSettings(**data.get("watchdog", {})),
            health_audit_110=HealthAudit110Settings(**data.get("health_audit_110", {})),
            storage=StorageSettings(**data.get("storage", {})),
            fixtures=FixtureSettings(**data.get("fixtures", {})),
            replay=ReplaySettings(**data.get("replay", {})),
            mlops=MLOpsSettings(**data.get("mlops", {})),
            llm=LLMSettings(**data.get("llm", {})),
            distributed=DistributedRuntimeSettings(**data.get("distributed", {})),
            universe_builder=UniverseBuilderSettings(**data.get("universe_builder", {})),
            autonomous=AutonomousDecisionSettings(**data.get("autonomous", {})),
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


    def live_provider(self) -> str:
        if "kraken_spot" in self.provider_whitelist:
            return "kraken_spot"
        return "binance_um_perps"

    def live_ordering_enabled(self) -> bool:
        mode = self.execution_mode_enum()
        return mode in {ExecutionMode.LIVE, ExecutionMode.LIVE_TESTNET}

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

        if mode == ExecutionMode.PAPER:
            return

        # Global live connector guard for non-paper execution modes.
        provider = self.live_provider()
        if provider not in self.provider_whitelist:
            raise ValueError(f"Live execution blocked: provider_whitelist missing {provider}")

        if mode == ExecutionMode.LIVE_READONLY:
            return

        missing = []
        enable_live = unlock.enable_live_trading or self.explicit_live_enable
        ack_live = unlock.ack_i_understand_risks or self.ack_live_risks

        if not enable_live:
            missing.append("ENABLE_LIVE_TRADING")
        if not ack_live:
            missing.append("ACK_I_UNDERSTAND_RISKS")
        if any(v == UNSPECIFIED for v in self._critical_risk_limits()):
            missing.append("critical risk limits")

        if provider == "kraken_spot":
            api_key = os.getenv(self.execution.kraken_spot.api_key_env, "")
            api_secret = os.getenv(self.execution.kraken_spot.api_secret_env, "")
            if not api_key or not api_secret:
                missing.append("kraken_spot_api_credentials")
        else:
            api_key = os.getenv(self.execution.binance.api_key_env, "")
            api_secret = os.getenv(self.execution.binance.api_secret_env, "")
            if not api_key or not api_secret:
                missing.append("binance_api_credentials")

        if mode == ExecutionMode.LIVE and unlock.canary_required_before_full and not self.canary_mode:
            missing.append("CANARY_MODE")
        if mode == ExecutionMode.LIVE and unlock.require_testnet_passed:
            if os.getenv("TESTNET_VALIDATED", "false").lower() not in {"1", "true", "yes", "on"}:
                missing.append("TESTNET_VALIDATED")
        if mode == ExecutionMode.LIVE and bool(unlock.require_operator_confirmation_artifact):
            if os.getenv("AUTONOMOUS_LIVE_GO", "false").lower() not in {"1", "true", "yes", "on"}:
                missing.append("AUTONOMOUS_LIVE_GO")
            confirmation_path = str(
                os.getenv(
                    "AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE",
                    str(unlock.operator_confirmation_file or ""),
                )
                or ""
            ).strip()
            if not confirmation_path:
                missing.append("AUTONOMOUS_LIVE_OPERATOR_CONFIRMATION_FILE")
            elif not Path(confirmation_path).exists():
                missing.append("LIVE_OPERATOR_CONFIRMATION_FILE")

        if missing:
            raise ValueError(f"Live trading blocked until configured: {missing}")


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
