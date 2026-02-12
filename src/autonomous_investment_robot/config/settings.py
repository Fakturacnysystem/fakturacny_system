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


@dataclass
class ExecutionSettings:
    mode: str = "paper"
    fee_bps: float = 2.0
    slippage_bps: float = 1.0
    partial_fill_ratio: float = 0.7


@dataclass
class PolicySettings:
    confidence_threshold: float = 0.55
    estimated_cost_bps: float = 3.0
    base_risk_budget: float = 1000.0


@dataclass
class MonitoringSettings:
    metrics_port: int = 9108


@dataclass
class StorageSettings:
    run_dir: str = "runs/latest"


@dataclass
class FixtureSettings:
    ohlcv_csv: str = "data/fixtures/btcusdt_1h.csv"


@dataclass
class ReplaySettings:
    source: str = "fixtures"


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
    policy: PolicySettings = field(default_factory=PolicySettings)
    monitoring: MonitoringSettings = field(default_factory=MonitoringSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    fixtures: FixtureSettings = field(default_factory=FixtureSettings)
    replay: ReplaySettings = field(default_factory=ReplaySettings)

    @classmethod
    def from_env(cls) -> "RobotSettings":
        mode = TradingMode(os.getenv("ROBOT_TRADING_MODE", "paper"))
        explicit = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
        ack = os.getenv("ACK_I_UNDERSTAND_RISKS", "false").lower() == "true"
        canary = os.getenv("CANARY_MODE", "false").lower() == "true"
        safe = os.getenv("ROBOT_SAFE_MODE_DEFAULT", "true").lower() == "true"
        providers = [p for p in os.getenv("ROBOT_PROVIDER_WHITELIST", "").split(",") if p]
        return cls(trading_mode=mode, explicit_live_enable=explicit, ack_live_risks=ack, canary_mode=canary, safe_mode_default=safe, provider_whitelist=providers)

    @classmethod
    def from_file(cls, path: str) -> "RobotSettings":
        data = _load_yaml_like(path)
        cfg = cls(
            trading_mode=TradingMode(data.get("mode", "paper")),
            explicit_live_enable=bool(data.get("enable_live_trading", False)),
            ack_live_risks=bool(data.get("ack_i_understand_risks", False)),
            canary_mode=bool(data.get("canary_mode", False)),
            safe_mode_default=bool(data.get("safe_mode_default", True)),
            provider_whitelist=list(data.get("provider_whitelist", [])),
            universe=list(data.get("universe", ["BTCUSDT"])),
            timeframe=data.get("timeframe", "1h"),
            risk=RiskLimits(**data.get("risk", {})),
            execution=ExecutionSettings(**data.get("execution", {})),
            policy=PolicySettings(**data.get("policy", {})),
            monitoring=MonitoringSettings(**data.get("monitoring", {})),
            storage=StorageSettings(**data.get("storage", {})),
            fixtures=FixtureSettings(**data.get("fixtures", {})),
            replay=ReplaySettings(**data.get("replay", {})),
        )
        return cfg

    def __post_init__(self) -> None:
        if isinstance(self.trading_mode, str):
            self.trading_mode = TradingMode(self.trading_mode)
        self._validate()

    def _validate(self) -> None:
        required = [
            self.risk.max_daily_loss_pct,
            self.risk.max_drawdown_pct,
            self.risk.max_position_notional,
            self.risk.max_exposure_notional,
            self.risk.max_orders_per_min,
            self.risk.leverage,
            self.risk.max_spread_bps,
            self.risk.min_depth_notional,
            self.risk.stale_data_seconds,
        ]
        if self.trading_mode == TradingMode.LIVE:
            missing = []
            if not self.explicit_live_enable:
                missing.append("ENABLE_LIVE_TRADING")
            if not self.ack_live_risks:
                missing.append("ACK_I_UNDERSTAND_RISKS")
            if not self.canary_mode:
                missing.append("CANARY_MODE")
            if any(v == UNSPECIFIED for v in required):
                missing.append("critical risk limits")
            if self.universe and len(self.universe) > 1:
                missing.append("canary requires max 1 symbol")
            if missing:
                raise ValueError(f"Live trading blocked until configured: {missing}")


def _load_yaml_like(path: str) -> dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        out = yaml.safe_load(text)
        if isinstance(out, dict):
            return out
    except Exception:
        pass
    return json.loads(text)
