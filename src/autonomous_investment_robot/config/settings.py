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
    api_key_env: str = "KRAKEN_SPOT_API_KEY"
    api_secret_env: str = "KRAKEN_SPOT_API_SECRET"
    request_timeout_s: float = 10.0
    rate_limit_rps: float = 3.0
    allow_unknown_permissions: bool = False
    event_feed_path: str = ""


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
class MarginSettings:
    enabled: bool = False
    max_leverage: int = 0
    isolated_only: bool = True
    reduce_only_emergency: bool = True
    require_explicit_opt_in: bool = True


@dataclass
class RobotSettings:
    config_schema_version: int = 2
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
            provider_whitelist=providers,
            execution=ExecutionSettings(mode=exec_mode),
            safety=SafetySettings(
                live_unlock=LiveUnlockSettings(
                    enable_live_trading=explicit,
                    ack_i_understand_risks=ack,
                    allow_full_live_stage=os.getenv("ENABLE_FULL_LIVE_STAGE", "false").lower() == "true",
                )
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

        return cls(
            trading_mode=TradingMode(data.get("mode", "paper")),
            explicit_live_enable=bool(data.get("enable_live_trading", False)) or env_enable_live,
            ack_live_risks=bool(data.get("ack_i_understand_risks", False)) or env_ack_live,
            canary_mode=bool(data.get("canary_mode", False)) or env_canary_mode,
            safe_mode_default=bool(data.get("safe_mode_default", True)),
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

    def rollout_stage(self) -> RolloutStage:
        mode = self.execution_mode_enum()
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
                and not self.canary_mode
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
            "doctrine_launch_safe": doctrine_launch_safe,
        }

    def config_hash(self) -> str:
        payload = json.dumps(self.config_manifest(), sort_keys=True, default=str)
        return sha256(payload.encode("utf-8")).hexdigest()

    def config_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.config_schema_version,
            "runtime_mode": self.execution_mode_enum().value,
            "rollout_stage": self.rollout_stage().value,
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
            },
            "live_gate_status": self.live_gate_status(),
            "monitoring": {
                "decision_latency_warn_ms": self.monitoring.decision_latency_warn_ms,
                "reconciliation_lag_warn_ms": self.monitoring.reconciliation_lag_warn_ms,
                "loop_latency_warn_ms": self.monitoring.loop_latency_warn_ms,
                "manual_review_ack_ttl_minutes": self.monitoring.manual_review_ack_ttl_minutes,
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
            missing.append("ENABLE_FULL_LIVE_STAGE")
        if mode == ExecutionMode.LIVE and unlock.require_testnet_passed:
            if os.getenv("TESTNET_VALIDATED", "false").lower() != "true":
                missing.append("TESTNET_VALIDATED")

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
