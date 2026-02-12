from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

UNSPECIFIED = "UNSPECIFIED"


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


@dataclass
class RiskLimits:
    max_daily_loss_pct: float | str = UNSPECIFIED
    max_drawdown_pct: float | str = UNSPECIFIED
    var_confidence: float | str = UNSPECIFIED
    var_horizon: str = UNSPECIFIED
    cvar_confidence: float | str = UNSPECIFIED
    cvar_horizon: str = UNSPECIFIED
    per_asset_cap: dict[str, float] | str = UNSPECIFIED
    per_venue_cap: dict[str, float] | str = UNSPECIFIED
    depth_usage_limit_pct: float | str = UNSPECIFIED
    max_spread_percentile: float | str = UNSPECIFIED


@dataclass
class ComplianceSettings:
    require_authorized_provider: bool = True
    mica_register_url: str = UNSPECIFIED
    travel_rule_enabled: bool = True
    allowed_providers: list[str] = field(default_factory=list)


@dataclass
class SecuritySettings:
    require_ip_allowlist: bool = True
    trading_key_withdrawals_disabled: bool = True
    key_rotation_days: int | str = UNSPECIFIED


@dataclass
class RobotSettings:
    trading_mode: TradingMode = TradingMode.PAPER
    explicit_live_enable: bool = False
    safe_mode_default: bool = True
    event_bus: str = "NATS"
    streaming_compute: str = UNSPECIFIED
    risk: RiskLimits = field(default_factory=RiskLimits)
    compliance: ComplianceSettings = field(default_factory=ComplianceSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)

    @classmethod
    def from_env(cls) -> "RobotSettings":
        mode = TradingMode(os.getenv("ROBOT_TRADING_MODE", "paper"))
        explicit = os.getenv("ROBOT_EXPLICIT_LIVE_ENABLE", "false").lower() == "true"
        safe = os.getenv("ROBOT_SAFE_MODE_DEFAULT", "true").lower() == "true"
        providers = os.getenv("ROBOT_COMPLIANCE__ALLOWED_PROVIDERS", "")
        c = ComplianceSettings(allowed_providers=[p for p in providers.split(",") if p])
        return cls(trading_mode=mode, explicit_live_enable=explicit, safe_mode_default=safe, compliance=c)

    def __post_init__(self) -> None:
        if self.trading_mode == TradingMode.LIVE:
            missing = []
            if not self.explicit_live_enable:
                missing.append("explicit_live_enable")
            critical = [
                self.risk.max_daily_loss_pct,
                self.risk.max_drawdown_pct,
                self.risk.var_confidence,
                self.risk.cvar_confidence,
                self.risk.depth_usage_limit_pct,
            ]
            if any(v == UNSPECIFIED for v in critical):
                missing.append("critical risk limits")
            if missing:
                raise ValueError(f"Live trading blocked until configured: {missing}")
