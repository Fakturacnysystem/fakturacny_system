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
    max_drawdown_pct: float | str = UNSPECIFIED
    max_position_notional: float | str = UNSPECIFIED
    max_exposure_notional: float | str = UNSPECIFIED
    max_orders_per_min: int | str = UNSPECIFIED
    leverage: int | str = UNSPECIFIED
    target_portfolio_vol: float | str = UNSPECIFIED
    cvar_limit_pct: float | str = UNSPECIFIED
    max_spread_bps: float | str = UNSPECIFIED
    min_depth_notional: float | str = UNSPECIFIED
    stale_data_seconds: float | str = UNSPECIFIED
    min_margin_buffer: float | str = UNSPECIFIED
    max_funding_cost_per_day: float | str = UNSPECIFIED
    max_oi_spike_pct: float | str = UNSPECIFIED
    max_liquidation_spike: float | str = UNSPECIFIED
    divergence_threshold_bps: float | str = UNSPECIFIED
    crowding_score_kill: float | str = UNSPECIFIED


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


@dataclass
class LiveUnlockSettings:
    enable_live_trading: bool = False
    ack_i_understand_risks: bool = False
    require_testnet_passed: bool = True
    canary_required_before_full: bool = True


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
    allocator: AllocatorSettings = field(default_factory=AllocatorSettings)
    monitoring: MonitoringSettings = field(default_factory=MonitoringSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    fixtures: FixtureSettings = field(default_factory=FixtureSettings)
    replay: ReplaySettings = field(default_factory=ReplaySettings)
    mlops: MLOpsSettings = field(default_factory=MLOpsSettings)

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
            ),
            safety=SafetySettings(live_unlock=LiveUnlockSettings(**live_unlock_data)),
            policy=PolicySettings(**data.get("policy", {})),
            tco=TCOSettings(**data.get("tco", {})),
            allocator=AllocatorSettings(**data.get("allocator", {})),
            monitoring=MonitoringSettings(**data.get("monitoring", {})),
            storage=StorageSettings(**data.get("storage", {})),
            fixtures=FixtureSettings(**data.get("fixtures", {})),
            replay=ReplaySettings(**data.get("replay", {})),
            mlops=MLOpsSettings(**data.get("mlops", {})),
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
        if "binance_um_perps" not in self.provider_whitelist:
            raise ValueError("Live execution blocked: provider_whitelist missing binance_um_perps")

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

        api_key = os.getenv(self.execution.binance.api_key_env, "")
        api_secret = os.getenv(self.execution.binance.api_secret_env, "")
        if not api_key or not api_secret:
            missing.append("binance_api_credentials")

        if mode == ExecutionMode.LIVE and unlock.canary_required_before_full and not self.canary_mode:
            missing.append("CANARY_MODE")
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
