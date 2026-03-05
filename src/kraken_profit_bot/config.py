from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class SymbolConfig(BaseModel):
    allowlist: list[str] = Field(default_factory=lambda: ["XBTUSD", "ETHUSD"])
    denylist: list[str] = Field(default_factory=list)


class MarketEnableConfig(BaseModel):
    spot: bool = True
    margin: bool = False
    perps: bool = True
    fix_adapter: bool = False


class FeesConfig(BaseModel):
    maker_fee_bps: float = 16.0
    taker_fee_bps: float = 26.0
    slippage_bps: float = 4.0
    assume_worst_case_taker_on_unknown: bool = True


class RiskConfig(BaseModel):
    max_notional_exposure_quote: float = 5000.0
    max_leverage: float = 3.0
    max_open_positions_per_symbol: int = 5
    max_order_rate_per_min: int = 120
    max_drawdown_pct_daily: float = 5.0
    max_spread_bps: float = 80.0
    stale_data_seconds: float = 5.0
    abnormal_volatility_sigma: float = 5.0


class CadenceConfig(BaseModel):
    order_submission_interval_seconds: int = 60
    strategy_loop_seconds: float = 1.0
    warmup_seconds: int = 20


class ProfitConfig(BaseModel):
    profit_target_net: float = 0.02
    ideal_profit_target_net: float = 0.05
    accounting_method: str = "fifo"

    @field_validator("profit_target_net")
    @classmethod
    def _enforce_min_profit(cls, value: float) -> float:
        if value < 0.02:
            raise ValueError("PROFIT_TARGET_NET cannot be lower than 0.02")
        return value

    @field_validator("accounting_method")
    @classmethod
    def _accounting_method(cls, value: str) -> str:
        v = value.lower().strip()
        if v not in {"fifo", "average"}:
            raise ValueError("accounting_method must be fifo or average")
        return v


class InstrumentConfig(BaseModel):
    min_order_size_by_symbol: dict[str, float] = Field(default_factory=dict)
    min_notional_by_symbol: dict[str, float] = Field(default_factory=dict)


class StorageConfig(BaseModel):
    sqlite_path: str = "runs/kraken_profit_bot/state.sqlite3"
    log_json_path: str = "runs/kraken_profit_bot/bot.jsonl"


class DataConfig(BaseModel):
    reconnect_backoff_initial_s: float = 1.0
    reconnect_backoff_max_s: float = 30.0
    health_check_seconds: float = 2.0


class ExchangeConfig(BaseModel):
    spot_rest_url: str = "https://api.kraken.com"
    spot_ws_v2_url: str = "wss://ws.kraken.com/v2"
    futures_rest_url: str = "https://futures.kraken.com"
    futures_ws_url: str = "wss://futures.kraken.com/ws/v1"


class BotConfig(BaseModel):
    symbols: SymbolConfig = Field(default_factory=SymbolConfig)
    markets: MarketEnableConfig = Field(default_factory=MarketEnableConfig)
    fees: FeesConfig = Field(default_factory=FeesConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    cadence: CadenceConfig = Field(default_factory=CadenceConfig)
    profit: ProfitConfig = Field(default_factory=ProfitConfig)
    instruments: InstrumentConfig = Field(default_factory=InstrumentConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    dry_run: bool = False

    @model_validator(mode="after")
    def _validate_lists(self) -> "BotConfig":
        deny = {s.upper() for s in self.symbols.denylist}
        allow = [s.upper() for s in self.symbols.allowlist if s.upper() not in deny]
        if not allow:
            raise ValueError("symbols.allowlist is empty after denylist filtering")
        self.symbols.allowlist = allow
        self.symbols.denylist = sorted(deny)
        return self


class Credentials(BaseModel):
    kraken_api_key: str = ""
    kraken_api_secret: str = ""
    kraken_futures_key: str = ""
    kraken_futures_secret: str = ""

    @property
    def has_spot(self) -> bool:
        return bool(self.kraken_api_key and self.kraken_api_secret)

    @property
    def has_futures(self) -> bool:
        return bool(self.kraken_futures_key and self.kraken_futures_secret)


def load_config(path: str | Path) -> BotConfig:
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")
    return BotConfig.model_validate(raw)


def load_credentials_from_env() -> Credentials:
    return Credentials(
        kraken_api_key=os.getenv("KRAKEN_API_KEY", "").strip(),
        kraken_api_secret=os.getenv("KRAKEN_API_SECRET", "").strip(),
        kraken_futures_key=os.getenv("KRAKEN_FUTURES_KEY", "").strip(),
        kraken_futures_secret=os.getenv("KRAKEN_FUTURES_SECRET", "").strip(),
    )


def default_config_dict() -> dict[str, Any]:
    return BotConfig().model_dump()
