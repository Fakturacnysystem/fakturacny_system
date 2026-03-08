from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any

from autonomous_investment_robot.config.settings import ExecutionMode, RobotSettings
from autonomous_investment_robot.connectors.cex.kraken_spot import (
    KrakenConnectorError,
    KrakenInsufficientFundsError,
    KrakenRateLimitError,
    KrakenSpotConnector,
)
from autonomous_investment_robot.services.exchange_constraints import ExchangeConstraintsOracle
from autonomous_investment_robot.services.execution.profit_gate import (
    AccountingMethod,
    PositionLot,
    ProfitGate,
    ProfitGateConfig,
)
from autonomous_investment_robot.services.execution.tp_ladder import TPLadderConfig, desired_tp_pct, ladder_floor_tp_pct
from autonomous_investment_robot.services.execution.exit_order_manager import (
    ExitOrderManager,
    ExitOrderManagerConfig,
)


AGGRESSIVE_HF_DEFAULTS: dict[str, str] = {
    "AUTONOMOUS_SYMBOL_TOPK": "60",
    "AUTONOMOUS_SYMBOL_SCORE_REFRESH_S": "5",
    "ORDER_SUBMISSION_INTERVAL_SECONDS": "60",
    "AUTONOMOUS_EXTRA_SUBMISSIONS_ENABLED": "true",
    "AUTONOMOUS_EXTRA_SUBMISSIONS_MAX_PER_MIN": "6",
    "AUTONOMOUS_PROBE_NOTIONAL_QUOTE": "1.50",
    "AUTONOMOUS_PROBE_DISTANCE_TICKS": "1",
    "AUTONOMOUS_ENTRY_FEE_BPS": "30.0",
    "AUTONOMOUS_EXIT_FEE_BPS": "30.0",
    "AUTONOMOUS_PROFIT_GATE_SLIPPAGE_BPS": "20.0",
    "AUTONOMOUS_SLIPPAGE_CALIBRATION_ENABLED": "true",
    "AUTONOMOUS_SLIPPAGE_CALIBRATION_PCTL": "0.90",
    "AUTONOMOUS_SLIPPAGE_CALIBRATION_MIN_BPS": "12.0",
    "AUTONOMOUS_SLIPPAGE_CALIBRATION_MAX_BPS": "80.0",
    "AUTONOMOUS_ENTRY_LADDER_ENABLED": "true",
    "AUTONOMOUS_ENTRY_LADDER_STEPS": "3",
    "AUTONOMOUS_ENTRY_LADDER_MAX_BPS": "10",
    "AUTONOMOUS_ENTRY_LADDER_MIN_STEP_BPS": "2",
    "AUTONOMOUS_ENTRY_LADDER_REFRESH_S": "5",
    "AUTONOMOUS_ENTRY_LADDER_ORDER_TTL_S": "60",
    "AUTONOMOUS_ENTRY_MAKER_ONLY": "true",
    "AUTONOMOUS_EXIT_REPRICE_INTERVAL_S": "10",
    "AUTONOMOUS_EXIT_MAX_ORDER_AGE_S": "600",
    "AUTONOMOUS_EXIT_CANCEL_REPLACE_MIN_MOVE_TICKS": "1",
    "AUTONOMOUS_EXIT_MIN_TIME_BETWEEN_REPRICE_S": "3",
    "AUTONOMOUS_EXIT_POST_ONLY": "true",
    "AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN": "60",
    "AUTONOMOUS_MAX_OPEN_ORDERS_GLOBAL": "120",
    "AUTONOMOUS_MAX_OPEN_ORDERS_PER_SYMBOL": "8",
    "AUTONOMOUS_CANCEL_REPLACE_BUDGET_PER_SYMBOL_PER_MIN": "12",
    "AUTONOMOUS_SPREAD_HIGH_BPS": "40.0",
    "AUTONOMOUS_BOOK_MIN_DEPTH_QUOTE": "120.0",
    "AUTONOMOUS_SYMBOL_QUARANTINE_MIN": "5",
    "AUTONOMOUS_INVENTORY_THROTTLE_ENABLED": "true",
    "AUTONOMOUS_INVENTORY_TARGET_NOTIONAL_QUOTE": "50.0",
    "AUTONOMOUS_INVENTORY_MAX_NOTIONAL_QUOTE": "150.0",
    "AUTONOMOUS_INVENTORY_THROTTLE_STEP": "0.15",
}


def _profile_name() -> str:
    return str(os.getenv("AUTONOMOUS_PROFILE", "") or "").strip().lower()


def _profile_default(name: str, default: str) -> str:
    if os.getenv(name) is not None:
        raw = os.getenv(name)
        return default if raw is None else str(raw)
    if _profile_name() == "aggressive_hf":
        return str(AGGRESSIVE_HF_DEFAULTS.get(name, default))
    return str(default)


def _env_float_profile(name: str, default: float) -> float:
    return _env_float(name, float(_profile_default(name, str(default))))


def _env_int_profile(name: str, default: int) -> int:
    raw = _profile_default(name, str(default))
    try:
        return int(float(raw))
    except Exception:
        return int(default)


def _env_bool_profile(name: str, default: bool) -> bool:
    raw = _profile_default(name, "true" if default else "false")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except Exception:
        return float(default)


@dataclass
class LiveExecutionResult:
    status: str
    reason: str = ""
    order: dict[str, Any] | None = None


@dataclass
class _IntentView:
    symbol: str
    side: str
    target_notional: float
    why: dict[str, Any]


@dataclass
class RejectTracker:
    timestamps: list[float] = field(default_factory=list)

    def add(self, ts: float) -> None:
        self.timestamps.append(ts)
        self.timestamps = [x for x in self.timestamps if ts - x <= 60.0]

    def storm(self, max_rejects: int) -> bool:
        return len(self.timestamps) > max_rejects


@dataclass
class RateLimitTracker:
    timestamps: list[float] = field(default_factory=list)

    def add(self, ts: float) -> None:
        self.timestamps.append(ts)
        self.timestamps = [x for x in self.timestamps if ts - x <= 60.0]

    def storm(self, max_hits: int) -> bool:
        return len(self.timestamps) > max_hits


@dataclass
class FillLedger:
    position_qty: float = 0.0
    avg_entry_price: float = 0.0
    position_open_ts: float | None = None
    realized_gross_quote: float = 0.0
    fees_quote: float = 0.0
    filled_notional_quote: float = 0.0
    order_attempts: int = 0
    order_fills: int = 0
    fill_events: int = 0
    trade_ids: set[str] = field(default_factory=set)
    shortfall_bps: list[float] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)
    latency_fast: int = 0
    latency_medium: int = 0
    latency_slow: int = 0
    bootstrapped_from_balance: bool = False
    lots: list[PositionLot] = field(default_factory=list)


class MarketSessionAdapter:
    """Drop-in session adapter; Kraken spot is 24/7 but this keeps venue-aware interface stable."""

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = bool(enabled)

    def is_open(self, pair: str, *, ts: float | None = None) -> tuple[bool, str]:
        _ = pair
        _ = ts
        if not self.enabled:
            return True, "session_adapter_disabled"
        return True, "always_open_24_7"


class KrakenMinOrderGuard:
    def __init__(self, connector: KrakenSpotConnector) -> None:
        self.connector = connector
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_ts: float = 0.0
        self._cache_ttl_s = max(60.0, float(os.getenv("AUTONOMOUS_CONSTRAINTS_TTL_S", "1800") or "1800"))
        self._last_load_error: str = ""

    def load_pairs(self) -> dict[str, dict[str, Any]]:
        now = time.time()
        if self._cache and (now - self._cache_ts) <= self._cache_ttl_s:
            return self._cache
        raw = self.connector.asset_pairs()
        if isinstance(raw, dict) and isinstance(raw.get("error"), list) and raw.get("error"):
            # Preserve last known-good cache on exchange-side parse errors.
            self._last_load_error = ",".join(str(x) for x in raw.get("error", []) if str(x))
            return dict(self._cache)
        if isinstance(raw, dict) and isinstance(raw.get("result"), dict):
            raw = raw.get("result", {})
        if not isinstance(raw, dict):
            self._cache = {}
            self._cache_ts = now
            return self._cache
        out: dict[str, dict[str, Any]] = {}
        for key, meta in raw.items():
            if not isinstance(meta, dict):
                continue
            out[str(key)] = meta
            alt = str(meta.get("altname", "") or "")
            ws = str(meta.get("wsname", "") or "")
            if alt:
                out.setdefault(alt, meta)
            if ws:
                out.setdefault(ws, meta)
                out.setdefault(ws.replace("/", ""), meta)
        self._cache = out
        self._cache_ts = now
        return self._cache

    def pair_meta(self, pair: str) -> dict[str, Any]:
        return self.load_pairs().get(pair, {})

    def constraint_snapshot(self, pair: str, reference_price: float) -> dict[str, Any]:
        meta = self.pair_meta(pair)
        ordermin = float(meta.get("ordermin", 0.0) or 0.0)
        costmin = float(meta.get("costmin", 0.0) or 0.0)
        pair_decimals = int(meta.get("pair_decimals", 8) or 8)
        lot_decimals = int(meta.get("lot_decimals", 8) or 8)
        tick_size = 10 ** (-max(0, pair_decimals))
        lot_step = 10 ** (-max(0, lot_decimals))
        min_notional_quote = max(costmin, ordermin * max(0.0, float(reference_price)))
        ordertypes = meta.get("ordertype", [])
        if not isinstance(ordertypes, list):
            ordertypes = []
        return {
            "min_notional_quote": min_notional_quote,
            "min_lot": ordermin,
            "min_cost_quote": costmin,
            "price_precision": pair_decimals,
            "volume_precision": lot_decimals,
            "tick_size": tick_size,
            "lot_step": lot_step,
            "order_types_allowed": [str(x) for x in ordertypes],
        }

    def round_volume(self, pair: str, volume: float) -> float:
        meta = self.pair_meta(pair)
        lot_decimals = int(meta.get("lot_decimals", 8) or 8)
        # Floor volume to lot precision so rounded notional does not overshoot free balance.
        scale = 10**max(0, lot_decimals)
        return math.floor(max(0.0, volume) * scale) / scale

    def round_price(self, pair: str, price: float) -> float:
        meta = self.pair_meta(pair)
        pair_decimals = int(meta.get("pair_decimals", 8) or 8)
        return round(max(0.0, price), pair_decimals)

    def validate(
        self,
        pair: str,
        volume: float,
        price: float,
        available_quote: float,
        *,
        side: str = "buy",
        available_base: float | None = None,
    ) -> tuple[bool, str]:
        pairs = self.load_pairs()
        meta = pairs.get(pair, {})
        ordermin = float(meta.get("ordermin", 0.0) or 0.0)
        pair_decimals = int(meta.get("pair_decimals", 8) or 8)
        lot_decimals = int(meta.get("lot_decimals", 8) or 8)
        if volume < ordermin:
            return False, "min_order_block"
        if round(volume, lot_decimals) != volume:
            return False, "qty_precision_block"
        if round(price, pair_decimals) != price:
            return False, "price_precision_block"
        if side == "buy" and volume * price > available_quote * 1.001:
            return False, "insufficient_balance_block"
        if side == "sell" and available_base is not None and volume > max(0.0, float(available_base)):
            return False, "insufficient_base_balance_block"
        return True, "ok"


class LiveKrakenSpotService:
    def __init__(self, settings: RobotSettings, run_id: str, connector: KrakenSpotConnector | None = None) -> None:
        self.settings = settings
        self.run_id = run_id
        self.connector = connector or KrakenSpotConnector(settings.execution.kraken_spot)
        self.safe_mode = False
        self.killed = False
        self.kill_reason = ""
        self.min_guard = KrakenMinOrderGuard(self.connector)
        self.rejects = RejectTracker()
        self.rate_limits = RateLimitTracker()
        self.cooldown_until_s = 0.0
        self.rate_limit_cooldown_until_s = 0.0
        self._temporary_lockout_until_s = 0.0
        self._recent_ids: dict[str, float] = {}
        self._recent_ttl_s = 600.0
        self._ledgers: dict[str, FillLedger] = {}
        self._order_meta: dict[str, dict[str, Any]] = {}
        self._ticker_cache: dict[str, dict[str, Any]] = {}
        self._balance_cache: dict[str, Any] = {}
        self._balance_cache_ts = 0.0
        self._trades_cache: dict[str, Any] = {}
        self._trades_cache_ts = 0.0
        self._last_ledger_sync_ts: dict[str, float] = {}
        self._ticker_ttl_s = max(0.1, float(os.getenv("AUTONOMOUS_KRAKEN_TICKER_TTL_S", "1.0") or "1.0"))
        self._balance_ttl_s = max(0.1, float(os.getenv("AUTONOMOUS_KRAKEN_BALANCE_TTL_S", "3.0") or "3.0"))
        self._trades_ttl_s = max(0.1, float(os.getenv("AUTONOMOUS_KRAKEN_TRADES_TTL_S", "2.0") or "2.0"))
        self._trades_sync_min_interval_s = max(0.0, float(os.getenv("AUTONOMOUS_TRADES_SYNC_MIN_INTERVAL_S", "2.0") or "2.0"))
        cooldown_env = os.getenv(
            "AUTONOMOUS_RATE_LIMIT_COOLDOWN_S",
            os.getenv("AUTONOMOUS_KRAKEN_RATE_LIMIT_COOLDOWN_S", "4.0"),
        )
        self._rate_limit_cooldown_s = max(0.25, float(cooldown_env or "4.0"))
        self._temporary_lockout_cooldown_s = max(
            self._rate_limit_cooldown_s,
            _env_float(
                "AUTONOMOUS_KRAKEN_TEMP_LOCKOUT_COOLDOWN_S",
                max(20.0, self._rate_limit_cooldown_s * 4.0),
            ),
        )
        self._rate_limit_storm_threshold = max(3, int(os.getenv("AUTONOMOUS_KRAKEN_RATE_LIMIT_STORM", "8") or "8"))
        self._max_consecutive_rejects = max(1, int(os.getenv("AUTONOMOUS_MAX_CONSEC_REJECTS", "5") or "5"))
        self._reject_cooldown_s = max(5.0, _env_float("AUTONOMOUS_REJECT_COOLDOWN_S", 120.0))
        self._exec_retry_attempts = max(1, int(os.getenv("AUTONOMOUS_KRAKEN_EXEC_RETRY_ATTEMPTS", "3") or "3"))
        self._exec_retry_backoff_s = max(0.05, float(os.getenv("AUTONOMOUS_KRAKEN_EXEC_BACKOFF_BASE_S", "0.25") or "0.25"))
        self._exec_retry_backoff_max_s = max(self._exec_retry_backoff_s, float(os.getenv("AUTONOMOUS_KRAKEN_EXEC_BACKOFF_MAX_S", "2.5") or "2.5"))
        self._bootstrap_balance_position = str(os.getenv("AUTONOMOUS_BOOTSTRAP_BALANCE_POSITION", "false") or "false").strip().lower() in {"1", "true", "yes", "on"}
        self._bootstrap_require_tradeable = str(os.getenv("AUTONOMOUS_BOOTSTRAP_REQUIRE_TRADEABLE", "true") or "true").strip().lower() in {"1", "true", "yes", "on"}
        self._spot_dust_accumulator_enabled = str(os.getenv("AUTONOMOUS_SPOT_DUST_ACCUMULATOR", "true") or "true").strip().lower() in {"1", "true", "yes", "on"}
        self._taker_fallback_enabled = _env_bool("AUTONOMOUS_KRAKEN_TAKER_FALLBACK", True)
        self._taker_fallback_buy_enabled = _env_bool("AUTONOMOUS_KRAKEN_TAKER_FALLBACK_BUY", self._taker_fallback_enabled)
        self._taker_fallback_sell_enabled = _env_bool("AUTONOMOUS_KRAKEN_TAKER_FALLBACK_SELL", self._taker_fallback_enabled)
        self._profit_target_net = max(0.0, _env_float("AUTONOMOUS_PROFIT_TARGET_NET", 0.02))
        self._tp_only_mode = _env_bool("AUTONOMOUS_TP_ONLY_MODE", False)
        self._tp_ladder_cfg = TPLadderConfig.from_env()
        # Enforce a configurable hard net-profit floor and round-trip break-even floor from costs.
        hard_floor_bps = max(
            0.0,
            _env_float("AUTONOMOUS_SPOT_SELL_HARD_FLOOR_BPS", 90.0),
        )
        self._sell_profit_lock_floor_bps = max(
            hard_floor_bps,
            (2.0 * float(self.settings.execution.fee_bps)) + (2.0 * float(self.settings.execution.slippage_bps)),
        )
        default_sell_profit_bps = max(self._sell_profit_lock_floor_bps, self._profit_target_net * 10000.0)
        self._sell_profit_lock_enabled = _env_bool("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK", True)
        self._sell_profit_lock_min_bps = max(
            0.0,
            _env_float("AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS", default_sell_profit_bps),
        )
        self._sell_profit_lock_min_bps = max(self._sell_profit_lock_min_bps, self._sell_profit_lock_floor_bps)
        self._sell_profit_lock_target_bps = max(
            self._sell_profit_lock_min_bps,
            _env_float("AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS", self._sell_profit_lock_min_bps),
        )
        self._sell_profit_lock_target_hold_s = max(
            0.0,
            _env_float("AUTONOMOUS_SPOT_SELL_TARGET_HOLD_S", 90.0),
        )
        self._sell_profit_lock_fatal_bypass = _env_bool("AUTONOMOUS_SPOT_SELL_PROFIT_LOCK_FATAL_BYPASS", False)
        # Nonstop mode: transient internal kills can auto-recover after cooldown.
        self._auto_recover_kill_enabled = _env_bool("AUTONOMOUS_AUTO_RECOVER_KILL", True)
        self._auto_recover_kill_min_cooldown_s = max(
            30.0,
            _env_float("AUTONOMOUS_AUTO_RECOVER_KILL_MIN_COOLDOWN_S", 300.0),
        )
        self._sell_profit_lock_require_cost_basis = _env_bool("AUTONOMOUS_SPOT_SELL_REQUIRE_COST_BASIS", True)
        self._sell_all_in_on_profit = _env_bool("AUTONOMOUS_SELL_ALL_IN_ON_PROFIT", False)
        self._tp_state_path = os.path.join(self.settings.storage.run_dir, "position_state.json")
        self._tp_peak_profit_pct: dict[str, float] = {}
        self._load_tp_state()
        accounting_method = str(os.getenv("AUTONOMOUS_POSITION_ACCOUNTING", "fifo") or "fifo").strip().lower()
        self._position_accounting_method: AccountingMethod = "average" if accounting_method == "average" else "fifo"
        self._entry_fee_bps = max(
            0.0,
            _env_float_profile(
                "AUTONOMOUS_ENTRY_FEE_BPS",
                max(30.0, float(self.settings.execution.fee_bps)),
            ),
        )
        self._exit_fee_bps = max(
            0.0,
            _env_float_profile(
                "AUTONOMOUS_EXIT_FEE_BPS",
                max(30.0, float(self.settings.execution.fee_bps)),
            ),
        )
        self._slippage_bps_profit_gate = max(
            0.1,
            _env_float_profile(
                "AUTONOMOUS_PROFIT_GATE_SLIPPAGE_BPS",
                max(15.0, float(self.settings.execution.slippage_bps)),
            ),
        )
        self._slippage_calibration_enabled = _env_bool_profile("AUTONOMOUS_SLIPPAGE_CALIBRATION_ENABLED", True)
        self._slippage_calibration_pctl = max(
            0.5,
            min(0.999, _env_float_profile("AUTONOMOUS_SLIPPAGE_CALIBRATION_PCTL", 0.95)),
        )
        self._slippage_calibration_min_bps = max(
            0.1,
            _env_float_profile("AUTONOMOUS_SLIPPAGE_CALIBRATION_MIN_BPS", 10.0),
        )
        self._slippage_calibration_max_bps = max(
            self._slippage_calibration_min_bps,
            _env_float_profile("AUTONOMOUS_SLIPPAGE_CALIBRATION_MAX_BPS", 60.0),
        )
        self._slippage_calibration_interval_s = max(
            30.0,
            _env_float("AUTONOMOUS_SLIPPAGE_CALIBRATION_INTERVAL_S", 60.0),
        )
        self._last_slippage_calibration_ts = 0.0
        self._stale_sell_block = _env_bool("AUTONOMOUS_STALE_SELL_BLOCK", True)
        self._safe_mode_block_stale_buy = _env_bool(
            "AUTONOMOUS_SAFE_MODE_BLOCK_STALE_BUY",
            _env_bool("AUTONOMOUS_BLOCK_BUY_ON_STALE_IN_SAFE_MODE", True),
        )
        self._sell_limit_only = _env_bool("AUTONOMOUS_SPOT_SELL_LIMIT_ONLY", True)
        self._sell_post_only_default = _env_bool_profile(
            "AUTONOMOUS_SPOT_SELL_POST_ONLY",
            _env_bool("AUTONOMOUS_EXIT_POST_ONLY", True),
        )
        self._sell_post_only_retry_ticks = max(1, int(os.getenv("AUTONOMOUS_SPOT_SELL_POST_ONLY_RETRY_TICKS", "3") or "3"))
        self._entry_ladder_enabled = _env_bool_profile("AUTONOMOUS_ENTRY_LADDER_ENABLED", True)
        self._entry_ladder_steps = max(1, _env_int_profile("AUTONOMOUS_ENTRY_LADDER_STEPS", 5))
        self._entry_ladder_max_bps = max(0.1, _env_float_profile("AUTONOMOUS_ENTRY_LADDER_MAX_BPS", 25.0))
        self._entry_ladder_min_step_bps = max(0.1, _env_float_profile("AUTONOMOUS_ENTRY_LADDER_MIN_STEP_BPS", 3.0))
        self._entry_ladder_min_notional = max(0.0, _env_float("AUTONOMOUS_ENTRY_LADDER_MIN_NOTIONAL", 250.0))
        self._entry_ladder_order_ttl_s = max(10.0, _env_float_profile("AUTONOMOUS_ENTRY_LADDER_ORDER_TTL_S", 120.0))
        self._entry_ladder_refresh_s = max(1.0, _env_float_profile("AUTONOMOUS_ENTRY_LADDER_REFRESH_S", 10.0))
        self._entry_maker_only = _env_bool_profile("AUTONOMOUS_ENTRY_MAKER_ONLY", True)
        self._probe_distance_ticks_default = max(1, _env_int_profile("AUTONOMOUS_PROBE_DISTANCE_TICKS", 1))
        self._exit_reprice_interval_s = max(5.0, _env_float_profile("AUTONOMOUS_EXIT_REPRICE_INTERVAL_S", 30.0))
        self._exit_max_order_age_s = max(30.0, _env_float_profile("AUTONOMOUS_EXIT_MAX_ORDER_AGE_S", 1800.0))
        self._exit_min_time_between_reprice_s = max(
            1.0,
            _env_float_profile("AUTONOMOUS_EXIT_MIN_TIME_BETWEEN_REPRICE_S", 10.0),
        )
        self._exit_cancel_replace_min_move_ticks = max(
            1,
            _env_int_profile("AUTONOMOUS_EXIT_CANCEL_REPLACE_MIN_MOVE_TICKS", 2),
        )
        self._max_cancel_replace_per_min = max(1, _env_int_profile("AUTONOMOUS_MAX_CANCEL_REPLACE_PER_MIN", 20))
        self._cancel_replace_budget_per_symbol_per_min = max(
            1,
            _env_int_profile("AUTONOMOUS_CANCEL_REPLACE_BUDGET_PER_SYMBOL_PER_MIN", 5),
        )
        self._max_open_orders_global = max(1, _env_int_profile("AUTONOMOUS_MAX_OPEN_ORDERS_GLOBAL", 50))
        self._max_open_orders_per_symbol = max(1, _env_int_profile("AUTONOMOUS_MAX_OPEN_ORDERS_PER_SYMBOL", 5))
        self._open_orders_ttl_s = max(1.0, _env_float("AUTONOMOUS_OPEN_ORDERS_TTL_S", 15.0))
        self._open_orders_cache: dict[str, Any] = {}
        self._open_orders_cache_ts = 0.0
        self._vol_regime_enabled = _env_bool("AUTONOMOUS_VOL_REGIME_ENABLED", _env_bool("AUTONOMOUS_REGIME_ENABLED", True))
        vol_high_z = max(0.25, _env_float("AUTONOMOUS_VOL_HIGH_Z", 2.0))
        vol_high_default = 0.0015 * (vol_high_z / 2.0)
        self._vol_high_threshold = max(1e-9, _env_float("AUTONOMOUS_VOL_HIGH_THRESHOLD", vol_high_default))
        self._vol_low_threshold = max(1e-9, _env_float("AUTONOMOUS_VOL_LOW_THRESHOLD", 0.0003))
        self._vol_high_notional_scale = max(0.05, min(1.0, _env_float("AUTONOMOUS_VOL_HIGH_NOTIONAL_SCALE", 0.5)))
        self._vol_high_slippage_mult = max(1.0, _env_float("AUTONOMOUS_VOL_HIGH_SLIPPAGE_MULT", 1.5))
        self._vol_high_ladder_spacing_mult = max(1.0, _env_float("AUTONOMOUS_VOL_HIGH_LADDER_SPACING_MULT", 1.5))
        self._microstructure_enabled = _env_bool("AUTONOMOUS_MICROSTRUCTURE_ENABLED", True)
        self._microstructure_mode = str(os.getenv("AUTONOMOUS_MICROSTRUCTURE_MODE", "momentum") or "momentum").strip().lower()
        self._microstructure_imbalance_threshold = max(
            0.0,
            min(1.0, _env_float("AUTONOMOUS_MICROSTRUCTURE_IMBALANCE_THRESHOLD", 0.10)),
        )
        self._fee_aware_sizing_enabled = _env_bool("AUTONOMOUS_FEE_AWARE_SIZING", True)
        self._fee_aware_edge_buffer_bps = max(0.0, _env_float("AUTONOMOUS_FEE_AWARE_EDGE_BUFFER_BPS", 15.0))
        self._no_trade_zone_enabled = _env_bool("AUTONOMOUS_NO_TRADE_ZONE_ENABLED", True)
        self._no_trade_zone_spread_bps = max(
            0.0,
            _env_float_profile("AUTONOMOUS_NO_TRADE_ZONE_SPREAD_BPS", _env_float_profile("AUTONOMOUS_SPREAD_HIGH_BPS", 25.0)),
        )
        self._no_trade_zone_min_top_qty = max(0.0, _env_float("AUTONOMOUS_NO_TRADE_ZONE_MIN_TOP_QTY", 0.01))
        self._book_min_depth_quote = max(0.0, _env_float_profile("AUTONOMOUS_BOOK_MIN_DEPTH_QUOTE", 200.0))
        self._expected_fill_prob_gate_enabled = _env_bool("AUTONOMOUS_EXPECTED_FILL_PROB_GATE", True)
        self._expected_fill_prob_min = max(0.01, min(1.0, _env_float("AUTONOMOUS_EXPECTED_FILL_PROB_MIN", 0.15)))
        self._endpoint_rate_limit_budget = max(1, int(os.getenv("AUTONOMOUS_ENDPOINT_RATE_LIMIT_BUDGET", "5") or "5"))
        self._endpoint_rate_limit_window_s = max(10.0, _env_float("AUTONOMOUS_ENDPOINT_RATE_LIMIT_WINDOW_S", 60.0))
        self._endpoint_retry_budget = max(1, int(os.getenv("AUTONOMOUS_ENDPOINT_RETRY_BUDGET", "2") or "2"))
        self._endpoint_retry_backoff_mult = max(1.0, _env_float("AUTONOMOUS_ENDPOINT_RETRY_BACKOFF_MULT", 1.35))
        self._mid_history: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=720))
        self._last_exit_reprice_ts: dict[str, float] = {}
        self._endpoint_rate_limit_hits: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=256))
        self._entry_ladder_last_submit_ts: dict[str, float] = {}
        self._pair_quarantine_until_s: dict[str, float] = {}
        self._pair_reject_counts: dict[str, int] = {}
        self._symbol_quarantine_min = max(1, _env_int_profile("AUTONOMOUS_SYMBOL_QUARANTINE_MIN", 15))
        self._dust_ignore_hours = max(1.0, _env_float("AUTONOMOUS_DUST_IGNORE_HOURS", 6.0))
        self._dust_ignore_until: dict[str, float] = {}
        self._balance_drift_monitor_enabled = _env_bool("AUTONOMOUS_BALANCE_DRIFT_MONITOR_ENABLED", True)
        self._balance_drift_threshold_base = max(1e-12, _env_float("AUTONOMOUS_BALANCE_DRIFT_THRESHOLD_BASE", 1e-5))
        self._balance_drift_check_interval_s = max(5.0, _env_float("AUTONOMOUS_BALANCE_DRIFT_CHECK_INTERVAL_S", 30.0))
        self._last_balance_drift_check_ts: dict[str, float] = {}
        self._fee_refresh_interval_s = max(60.0, _env_float("AUTONOMOUS_FEE_REFRESH_INTERVAL_S", 21600.0))
        self._last_fee_refresh_ts = 0.0
        self._last_trade_volume_hint = 0.0
        self._fee_refresh_volume_jump_ratio = max(0.0, _env_float("AUTONOMOUS_FEE_REFRESH_VOLUME_JUMP_RATIO", 0.25))
        self._pnl_reconcile_interval_s = max(60.0, _env_float("AUTONOMOUS_PNL_RECONCILE_INTERVAL_S", 3600.0))
        self._last_pnl_reconcile_ts: dict[str, float] = {}
        self._exits_only_mode_until_s = 0.0
        self._exits_only_reason = ""
        self._entry_block_after_failed_probes_n = max(
            1,
            int(os.getenv("AUTONOMOUS_NO_NEW_ENTRIES_AFTER_FAILED_PROBES_N", "5") or "5"),
        )
        self._entry_block_cooldown_s = max(
            30.0,
            _env_float("AUTONOMOUS_ENTRY_BLOCK_COOLDOWN_S", 300.0),
        )
        self._failed_probe_streak = 0
        self._entries_blocked_until_health_ok = False
        self._entries_blocked_until_ts = 0.0
        self._session_adapter_enabled = _env_bool("AUTONOMOUS_SESSION_AWARENESS_ENABLED", True)
        self._session_adapter = MarketSessionAdapter(enabled=self._session_adapter_enabled)
        self._position_age_escalation_enabled = _env_bool("AUTONOMOUS_POSITION_AGE_ESCALATION_ENABLED", True)
        self._position_age_escalation_s = max(60.0, _env_float("AUTONOMOUS_POSITION_AGE_ESCALATION_S", 3600.0))
        self._position_age_entry_scale = max(0.05, min(1.0, _env_float("AUTONOMOUS_POSITION_AGE_ENTRY_SCALE", 0.5)))
        self._inventory_throttle_enabled = _env_bool_profile("AUTONOMOUS_INVENTORY_THROTTLE_ENABLED", False)
        self._inventory_target_notional_quote = max(0.0, _env_float_profile("AUTONOMOUS_INVENTORY_TARGET_NOTIONAL_QUOTE", 50.0))
        self._inventory_max_notional_quote = max(
            self._inventory_target_notional_quote,
            _env_float_profile("AUTONOMOUS_INVENTORY_MAX_NOTIONAL_QUOTE", 150.0),
        )
        self._inventory_throttle_step = max(0.0, min(1.0, _env_float_profile("AUTONOMOUS_INVENTORY_THROTTLE_STEP", 0.15)))
        self.profit_gate = ProfitGate(
            ProfitGateConfig(
                min_net_profit_ratio=self._profit_target_net,
                default_entry_fee_bps=self._entry_fee_bps,
                default_exit_fee_bps=self._exit_fee_bps,
                default_slippage_bps=self._slippage_bps_profit_gate,
                accounting_method=self._position_accounting_method,
            )
        )
        # Keep a small base buffer so rounding/cache jitter does not trigger exchange-side insufficient-funds rejects.
        self._sell_balance_buffer = min(1.0, max(0.90, _env_float("AUTONOMOUS_SELL_BALANCE_BUFFER", 0.985)))
        constraints_ttl = max(60.0, float(os.getenv("AUTONOMOUS_CONSTRAINTS_TTL_S", "1800") or "1800"))
        self.constraints_oracle = ExchangeConstraintsOracle(
            connector=self.connector,
            run_dir=self.settings.storage.run_dir,
            ttl_s=constraints_ttl,
        )
        trades_since_raw = os.getenv("AUTONOMOUS_TRADES_HISTORY_SINCE_TS", "").strip()
        if trades_since_raw:
            self._trades_history_since_ts = max(0.0, float(trades_since_raw))
        else:
            lookback_s = max(0.0, float(os.getenv("AUTONOMOUS_TRADES_HISTORY_LOOKBACK_S", "30") or "30"))
            self._trades_history_since_ts = max(0.0, time.time() - lookback_s)
        seed_pair = self.settings.universe[0] if self.settings.universe else None
        self._refresh_fee_profile(pair=seed_pair)
        self.exit_order_manager = ExitOrderManager(
            connector=self.connector,
            min_guard=self.min_guard,
            config=ExitOrderManagerConfig(
                reprice_interval_s=self._exit_reprice_interval_s,
                max_order_age_s=self._exit_max_order_age_s,
                cancel_replace_min_move_ticks=self._exit_cancel_replace_min_move_ticks,
                min_time_between_reprice_s=self._exit_min_time_between_reprice_s,
                post_only_default=self._sell_post_only_default,
                max_cancel_replace_per_min=self._max_cancel_replace_per_min,
                cancel_replace_budget_per_symbol_per_min=self._cancel_replace_budget_per_symbol_per_min,
            ),
            call_with_retry=self._call_with_retry,
            round_price_up_to_tick=self._round_price_up_to_tick,
        )

    def _record_midpoint(self, pair: str, mid: float, ts: float) -> None:
        if mid <= 0.0:
            return
        hist = self._mid_history[pair]
        hist.append((float(ts), float(mid)))
        cutoff = float(ts) - 900.0
        while hist and hist[0][0] < cutoff:
            hist.popleft()

    def _realized_volatility(self, pair: str, *, window_s: float = 300.0) -> float:
        hist = self._mid_history.get(pair)
        if not hist:
            return 0.0
        now = time.time()
        points = [(ts, px) for ts, px in hist if (now - ts) <= max(5.0, float(window_s)) and px > 0.0]
        if len(points) < 3:
            return 0.0
        log_returns: list[float] = []
        prev = points[0][1]
        for _ts, px in points[1:]:
            if prev > 0.0 and px > 0.0:
                log_returns.append(math.log(px / prev))
            prev = px
        if len(log_returns) < 2:
            return 0.0
        mean = sum(log_returns) / len(log_returns)
        var = sum((x - mean) ** 2 for x in log_returns) / max(1, len(log_returns) - 1)
        return math.sqrt(max(0.0, var))

    def _volatility_adjustments(self, pair: str) -> dict[str, float | str]:
        if not self._vol_regime_enabled:
            return {"regime": "normal", "notional_scale": 1.0, "slippage_mult": 1.0, "ladder_spacing_mult": 1.0}
        rv = self._realized_volatility(pair)
        if rv >= self._vol_high_threshold:
            return {
                "regime": "high",
                "realized_vol": rv,
                "notional_scale": self._vol_high_notional_scale,
                "slippage_mult": self._vol_high_slippage_mult,
                "ladder_spacing_mult": self._vol_high_ladder_spacing_mult,
            }
        if rv <= self._vol_low_threshold:
            return {"regime": "low", "realized_vol": rv, "notional_scale": 1.0, "slippage_mult": 1.0, "ladder_spacing_mult": 0.85}
        return {"regime": "normal", "realized_vol": rv, "notional_scale": 1.0, "slippage_mult": 1.0, "ladder_spacing_mult": 1.0}

    def _microstructure_metrics(self, bid: float, ask: float, bid_qty: float, ask_qty: float) -> dict[str, float]:
        denom = max(1e-9, bid_qty + ask_qty)
        imbalance = (bid_qty - ask_qty) / denom
        microprice = ((ask * bid_qty) + (bid * ask_qty)) / denom
        return {"imbalance": imbalance, "microprice": microprice}

    def _entry_allowed_by_microstructure(self, side: str, metrics: dict[str, float]) -> tuple[bool, str]:
        if not self._microstructure_enabled:
            return True, "microstructure_disabled"
        imbalance = float(metrics.get("imbalance", 0.0))
        threshold = float(self._microstructure_imbalance_threshold)
        side_n = str(side).lower()
        if side_n not in {"buy", "sell"}:
            return True, "microstructure_side_na"
        if self._microstructure_mode == "mean_reversion":
            if side_n == "buy" and imbalance >= -threshold:
                return False, "microstructure_no_mean_reversion_buy"
            if side_n == "sell" and imbalance <= threshold:
                return False, "microstructure_no_mean_reversion_sell"
        else:
            if side_n == "buy" and imbalance <= threshold:
                return False, "microstructure_no_momentum_buy"
            if side_n == "sell" and imbalance >= -threshold:
                return False, "microstructure_no_momentum_sell"
        return True, "microstructure_ok"

    def _fee_aware_entry_allows(self, intent, spread_bps: float, slippage_bps: float) -> tuple[bool, dict[str, float]]:
        if not self._fee_aware_sizing_enabled:
            return True, {}
        comps = intent.why.get("components", []) if isinstance(intent.why, dict) else []
        if not isinstance(comps, list) or not comps:
            return True, {}
        best_edge_bps = max(float(c.get("final_edge_bps", c.get("edge_bps", 0.0)) or 0.0) for c in comps)
        required_move_bps = (
            float(self._sell_profit_lock_min_bps)
            + float(self._entry_fee_bps)
            + float(self._exit_fee_bps)
            + (2.0 * float(slippage_bps))
            + max(0.0, float(spread_bps))
            + float(self._fee_aware_edge_buffer_bps)
        )
        return best_edge_bps >= required_move_bps, {
            "best_edge_bps": best_edge_bps,
            "required_move_bps": required_move_bps,
            "spread_bps": float(spread_bps),
            "slippage_bps": float(slippage_bps),
        }

    def _is_post_only_reject(self, exc: Exception | str) -> bool:
        txt = str(exc).lower()
        return "post only" in txt or "post-only" in txt or "would execute immediately" in txt

    def _sell_invariant_failure(self, pair: str, reason: str, details: dict[str, Any] | None = None) -> None:
        self.safe_mode = True
        self.kill_reason = reason
        self.cooldown_until_s = max(self.cooldown_until_s, time.time() + max(60.0, self._auto_recover_kill_min_cooldown_s))
        _ = pair
        _ = details

    def _enforce_sell_profit_invariant(
        self,
        *,
        pair: str,
        bid: float,
        ask: float,
        qty: float,
        gate_details: dict[str, Any],
        slippage_bps: float,
    ) -> tuple[bool, str]:
        required_ratio = float(gate_details.get("required_net_profit_ratio", self._profit_target_net) or self._profit_target_net)
        if required_ratio < self._profit_target_net:
            self._sell_invariant_failure(pair, "sell_invariant_required_ratio_below_floor", gate_details)
            return False, "sell_invariant_required_ratio_below_floor"
        blocked, check = self._sell_profit_lock_violation(
            pair=pair,
            bid=bid,
            ask=ask,
            intent=_IntentView(symbol=pair, side="sell", target_notional=max(0.0, qty * bid), why={"invariant": True}),
            target_exit_qty=qty,
            slippage_bps_override=slippage_bps,
        )
        if blocked:
            self._sell_invariant_failure(pair, "sell_invariant_profit_gate_blocked", check)
            return False, "sell_invariant_profit_gate_blocked"
        return True, "ok"

    def _round_price_up_to_tick(self, pair: str, price: float) -> float:
        meta = self.min_guard.pair_meta(pair)
        pair_decimals = int(meta.get("pair_decimals", 8) or 8)
        tick = 10 ** (-max(0, pair_decimals))
        px = math.ceil(max(0.0, float(price)) / max(tick, 1e-12)) * tick
        return self.min_guard.round_price(pair, px)

    def _round_volume_down_to_step(self, pair: str, qty: float) -> float:
        return self.min_guard.round_volume(pair, max(0.0, float(qty)))

    def _load_tp_state(self) -> None:
        self._tp_peak_profit_pct = {}
        path = str(self._tp_state_path or "")
        if not path:
            return
        try:
            if not os.path.exists(path):
                return
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                return
            for symbol, row in raw.items():
                if not isinstance(row, dict):
                    continue
                self._tp_peak_profit_pct[str(symbol).upper()] = float(row.get("peak_profit_pct", 0.0) or 0.0)
        except Exception:
            self._tp_peak_profit_pct = {}

    def _save_tp_state(self, pair: str, peak_profit_pct: float) -> None:
        path = str(self._tp_state_path or "")
        if not path:
            return
        try:
            payload: dict[str, Any] = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    prev = json.load(fh)
                if isinstance(prev, dict):
                    payload = prev
            key = str(pair).upper()
            row = payload.get(key)
            if not isinstance(row, dict):
                row = {}
                payload[key] = row
            row["peak_profit_pct"] = float(peak_profit_pct)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, sort_keys=True, indent=2)
        except Exception:
            pass

    def _desired_tp_pct_for_sell(
        self,
        *,
        pair: str,
        hold_s: float,
        avg_entry_price: float,
        bid: float,
        intent: Any,
    ) -> tuple[float, float, float]:
        baseline_min_tp_pct = max(
            float(self._profit_target_net) * 100.0,
            float(os.getenv("AUTONOMOUS_MIN_TAKE_PROFIT_PCT", "0.9") or "0.9"),
        )
        # Backward-compatible behavior: when TP ladder is disabled, keep a stable
        # fixed threshold and do not let historical peak state unexpectedly raise
        # required profit for legacy profit-lock tests.
        if not bool(self._tp_ladder_cfg.enabled):
            return float(baseline_min_tp_pct), float(baseline_min_tp_pct), 0.0
        sym = str(pair).upper()
        current_profit_pct = 0.0
        if avg_entry_price > 0.0 and bid > 0.0:
            current_profit_pct = ((bid - avg_entry_price) / max(avg_entry_price, 1e-12)) * 100.0
        peak_profit = max(float(self._tp_peak_profit_pct.get(sym, 0.0) or 0.0), float(current_profit_pct))
        self._tp_peak_profit_pct[sym] = peak_profit
        self._save_tp_state(sym, peak_profit)
        why = intent.why if hasattr(intent, "why") and isinstance(intent.why, dict) else {}
        confidence = float(why.get("fc_confidence", 0.0) or 0.0)
        regime = str(why.get("regime", why.get("market_regime", "")) or "")
        toxicity = float(why.get("toxicity_score", 0.0) or 0.0)
        floor = ladder_floor_tp_pct(hold_s=hold_s, cfg=self._tp_ladder_cfg, baseline_pct=baseline_min_tp_pct)
        desired = desired_tp_pct(
            hold_s=hold_s,
            baseline_pct=baseline_min_tp_pct,
            cfg=self._tp_ladder_cfg,
            confidence=confidence,
            regime=regime,
            toxicity_score=toxicity,
            peak_profit_pct=peak_profit,
        )
        desired = max(floor, desired)
        if self._tp_only_mode:
            desired = max(desired, baseline_min_tp_pct)
        return float(floor), float(desired), float(peak_profit)

    def set_exits_only_mode(self, *, reason: str, duration_s: float = 180.0) -> None:
        self._exits_only_mode_until_s = max(self._exits_only_mode_until_s, time.time() + max(1.0, float(duration_s)))
        self._exits_only_reason = str(reason or "exits_only_mode")

    def clear_exits_only_mode(self) -> None:
        self._exits_only_mode_until_s = 0.0
        self._exits_only_reason = ""

    def set_health_ok(self, ok: bool) -> None:
        if bool(ok):
            self._entries_blocked_until_health_ok = False
            self._failed_probe_streak = 0
            self._entries_blocked_until_ts = 0.0
            self.clear_exits_only_mode()

    def _entry_block_active(self, now_ts: float | None = None) -> bool:
        if not self._entries_blocked_until_health_ok:
            return False
        now = time.time() if now_ts is None else float(now_ts)
        until = float(self._entries_blocked_until_ts or 0.0)
        if until > 0.0 and now >= until:
            self._entries_blocked_until_health_ok = False
            self._failed_probe_streak = 0
            self._entries_blocked_until_ts = 0.0
            if self._exits_only_reason == "failed_probe_streak":
                self.clear_exits_only_mode()
            return False
        return True

    def _mark_dust(self, asset: str) -> None:
        if not asset:
            return
        self._dust_ignore_until[str(asset)] = time.time() + (self._dust_ignore_hours * 3600.0)

    def _is_asset_dust_ignored(self, asset: str) -> bool:
        if not asset:
            return False
        until = float(self._dust_ignore_until.get(str(asset), 0.0) or 0.0)
        return until > time.time()

    def _is_pair_quarantined(self, pair: str) -> bool:
        until = float(self._pair_quarantine_until_s.get(str(pair), 0.0) or 0.0)
        return until > time.time()

    def _quarantine_pair(self, pair: str, *, minutes: int | None = None) -> None:
        mins = self._symbol_quarantine_min if minutes is None else max(1, int(minutes))
        self._pair_quarantine_until_s[str(pair)] = max(
            float(self._pair_quarantine_until_s.get(str(pair), 0.0) or 0.0),
            time.time() + (mins * 60.0),
        )

    def _record_probe_result(self, *, is_probe: bool, success: bool, reason: str = "") -> None:
        if not is_probe:
            return
        now = time.time()
        reason_l = str(reason or "").strip().lower()
        ignored_failures = {
            "entries_blocked_until_health_ok",
            "exits_only_mode",
            "insufficient_balance_block",
            "inventory_throttle_max",
            "no_trade_zone",
            "expected_fill_probability_low",
            "stale_market_data_buy_block",
            "symbol_quarantine",
            "session_closed",
        }
        if reason_l in ignored_failures:
            return
        if success:
            self._failed_probe_streak = 0
            self._entries_blocked_until_health_ok = False
            self._entries_blocked_until_ts = 0.0
            return
        if self._entry_block_active(now):
            return
        self._failed_probe_streak += 1
        if self._failed_probe_streak >= self._entry_block_after_failed_probes_n:
            self._entries_blocked_until_health_ok = True
            self._entries_blocked_until_ts = now + self._entry_block_cooldown_s
            self.set_exits_only_mode(reason="failed_probe_streak", duration_s=max(120.0, self._auto_recover_kill_min_cooldown_s))

    def _orderbook_sanity_for_entry(self, *, bid: float, ask: float, bid_qty: float, ask_qty: float, spread_bps: float) -> tuple[bool, str]:
        vals = [bid, ask, bid_qty, ask_qty, spread_bps]
        if any((not math.isfinite(float(v))) for v in vals):
            return False, "orderbook_sanity_nan"
        if bid <= 0.0 or ask <= 0.0 or ask < bid:
            return False, "orderbook_sanity_invalid_prices"
        if bid_qty < 0.0 or ask_qty < 0.0:
            return False, "orderbook_sanity_negative_qty"
        if spread_bps <= 0.0:
            return False, "orderbook_sanity_zero_spread"
        return True, "ok"

    def _expected_fill_probability_allows(
        self,
        *,
        pair: str,
        bid: float,
        ask: float,
        bid_qty: float,
        ask_qty: float,
        spread_bps: float,
    ) -> tuple[bool, dict[str, float]]:
        if not self._expected_fill_prob_gate_enabled:
            return True, {}
        ledger = self._ledger_for(pair)
        hist_fill_prob = 0.0 if ledger.order_attempts <= 0 else (ledger.order_fills + 1.0) / (ledger.order_attempts + 2.0)
        depth_quote = min(max(0.0, bid_qty * bid), max(0.0, ask_qty * ask))
        spread_factor = max(0.0, min(1.0, 1.0 - (spread_bps / max(1.0, self._no_trade_zone_spread_bps * 1.5))))
        depth_factor = max(0.0, min(1.0, depth_quote / max(1e-9, self._book_min_depth_quote)))
        expected_fill_prob = 0.5 * hist_fill_prob + 0.25 * spread_factor + 0.25 * depth_factor
        ok = expected_fill_prob >= self._expected_fill_prob_min and depth_quote >= self._book_min_depth_quote
        return ok, {
            "expected_fill_prob": float(expected_fill_prob),
            "min_expected_fill_prob": float(self._expected_fill_prob_min),
            "depth_quote": float(depth_quote),
            "min_depth_quote": float(self._book_min_depth_quote),
            "hist_fill_prob": float(hist_fill_prob),
            "spread_bps": float(spread_bps),
        }

    def _open_order_counts(self, pair: str) -> tuple[int, int]:
        if not hasattr(self.connector, "open_orders"):
            return 0, 0
        now = time.time()
        raw: Any = None
        if self._open_orders_cache and (now - self._open_orders_cache_ts) <= self._open_orders_ttl_s:
            raw = self._open_orders_cache
        else:
            try:
                raw = self.connector.open_orders()
                if isinstance(raw, dict):
                    self._open_orders_cache = raw
                    self._open_orders_cache_ts = now
            except Exception:
                raw = self._open_orders_cache if self._open_orders_cache else None
        if raw is None:
            return 0, 0
        rows = raw.get("open", raw) if isinstance(raw, dict) else {}
        if not isinstance(rows, dict):
            return 0, 0
        total = 0
        for_symbol = 0
        for row in rows.values():
            if not isinstance(row, dict):
                continue
            total += 1
            descr = row.get("descr", {}) if isinstance(row.get("descr"), dict) else {}
            opair = str(descr.get("pair", row.get("pair", "")) or "")
            if opair and self._trade_matches_pair(opair, pair):
                for_symbol += 1
        return total, for_symbol

    def _open_order_limits_allow(self, pair: str, side: str) -> tuple[bool, str]:
        _ = side
        total, per_symbol = self._open_order_counts(pair)
        if total >= self._max_open_orders_global:
            return False, "max_open_orders_global"
        if per_symbol >= self._max_open_orders_per_symbol:
            return False, "max_open_orders_per_symbol"
        return True, "ok"

    def _maybe_calibrate_slippage(self, now_ts: float | None = None) -> None:
        if not self._slippage_calibration_enabled:
            return
        now = time.time() if now_ts is None else float(now_ts)
        if (now - self._last_slippage_calibration_ts) < self._slippage_calibration_interval_s:
            return
        self._last_slippage_calibration_ts = now
        samples: list[float] = []
        for ledger in self._ledgers.values():
            for v in ledger.shortfall_bps[-400:]:
                if math.isfinite(float(v)):
                    samples.append(abs(float(v)))
        if len(samples) < 8:
            return
        pctl = self._quantile(samples, self._slippage_calibration_pctl)
        calibrated = min(self._slippage_calibration_max_bps, max(self._slippage_calibration_min_bps, pctl))
        self._slippage_bps_profit_gate = float(calibrated)
        self.profit_gate.config.default_slippage_bps = float(calibrated)

    def _maybe_refresh_fee_profile(self, *, pair: str | None = None) -> None:
        now = time.time()
        if (now - self._last_fee_refresh_ts) >= self._fee_refresh_interval_s:
            self._refresh_fee_profile(pair=pair)
            self._last_fee_refresh_ts = now
            return
        if not hasattr(self.connector, "trade_volume"):
            return
        try:
            raw = self.connector.trade_volume(pair=pair, fee_info=True)  # type: ignore[attr-defined]
        except Exception:
            return
        volume_hint = 0.0
        if isinstance(raw, dict):
            for key in ("volume", "vol", "currentVolume"):
                if key in raw:
                    try:
                        volume_hint = max(volume_hint, float(raw.get(key) or 0.0))
                    except Exception:
                        pass
        if self._last_trade_volume_hint <= 0.0:
            self._last_trade_volume_hint = volume_hint
            return
        jump = (volume_hint - self._last_trade_volume_hint) / max(self._last_trade_volume_hint, 1e-9)
        if jump >= self._fee_refresh_volume_jump_ratio:
            self._refresh_fee_profile(pair=pair)
            self._last_fee_refresh_ts = now
            self._last_trade_volume_hint = max(self._last_trade_volume_hint, volume_hint)

    def _maybe_balance_drift_refresh(self, *, pair: str, available_base: float, mark_price: float) -> None:
        if not self._balance_drift_monitor_enabled:
            return
        now = time.time()
        last = float(self._last_balance_drift_check_ts.get(pair, 0.0) or 0.0)
        if (now - last) < self._balance_drift_check_interval_s:
            return
        self._last_balance_drift_check_ts[pair] = now
        ledger = self._ledger_for(pair)
        drift = abs(float(available_base) - float(ledger.position_qty))
        if drift < self._balance_drift_threshold_base:
            return
        self._balance_cache_ts = 0.0
        self._trades_cache_ts = 0.0
        try:
            self.sync_fill_ledger(pair, mark_price=max(0.0, float(mark_price)))
        except Exception:
            pass

    def _maybe_hourly_pnl_reconcile(self, *, pair: str, mark_price: float) -> None:
        now = time.time()
        last = float(self._last_pnl_reconcile_ts.get(pair, 0.0) or 0.0)
        if (now - last) < self._pnl_reconcile_interval_s:
            return
        self._last_pnl_reconcile_ts[pair] = now
        ledger = self._ledger_for(pair)
        # Avoid touching sync cadence for brand-new symbols without trade state.
        if ledger.position_qty <= 0.0 and not ledger.trade_ids and not ledger.lots:
            return
        try:
            self.sync_fill_ledger(pair, mark_price=max(0.0, float(mark_price)))
        except Exception:
            pass

    def _endpoint_rate_limit_count(self, stage: str, now_ts: float | None = None) -> int:
        now = time.time() if now_ts is None else float(now_ts)
        dq = self._endpoint_rate_limit_hits[stage]
        dq.append(now)
        while dq and (now - dq[0]) > self._endpoint_rate_limit_window_s:
            dq.popleft()
        return len(dq)

    def _entry_ladder_prices(self, pair: str, mid: float, spacing_mult: float) -> list[float]:
        if mid <= 0.0:
            return []
        steps = max(1, int(self._entry_ladder_steps))
        max_bps = float(self._entry_ladder_max_bps) * max(1.0, float(spacing_mult))
        min_step = float(self._entry_ladder_min_step_bps) * max(1.0, float(spacing_mult))
        out: list[float] = []
        for idx in range(steps):
            level_bps = min(max_bps, min_step * float(idx + 1))
            level_px = mid * (1.0 - (level_bps / 10000.0))
            out.append(self.min_guard.round_price(pair, level_px))
        return [p for p in out if p > 0.0]

    def _submit_entry_ladder(
        self,
        *,
        pair: str,
        quote_usable: float,
        target_notional: float,
        bid: float,
        ask: float,
        quote_ccy: str,
        vol_adjust: dict[str, float | str],
        userref_seed: int,
    ) -> LiveExecutionResult | None:
        if not self._entry_ladder_enabled:
            return None
        if target_notional < self._entry_ladder_min_notional:
            return None
        if quote_usable <= 0.0 or ask <= 0.0:
            return None
        ok_open, _open_reason = self._open_order_limits_allow(pair, "buy")
        if not ok_open:
            return None
        now = time.time()
        last_submit = float(self._entry_ladder_last_submit_ts.get(pair, 0.0) or 0.0)
        if (now - last_submit) < self._entry_ladder_refresh_s:
            return None
        if now < self.rate_limit_cooldown_until_s:
            return self._rate_limit_cooldown_result({"pair": pair, "stage": "entry_ladder_submit"})
        if hasattr(self.connector, "open_orders"):
            try:
                open_raw = self.connector.open_orders()
                open_rows = open_raw.get("open", open_raw) if isinstance(open_raw, dict) else {}
                if isinstance(open_rows, dict):
                    for txid, row in open_rows.items():
                        if not isinstance(row, dict):
                            continue
                        descr = row.get("descr", {}) if isinstance(row.get("descr"), dict) else {}
                        opair = str(descr.get("pair", row.get("pair", "")) or "")
                        otype = str(descr.get("type", row.get("type", "")) or "").lower()
                        if opair and not self._trade_matches_pair(opair, pair):
                            continue
                        if otype != "buy":
                            continue
                        opentm = float(row.get("opentm", row.get("open_ts", now)) or now)
                        if (now - opentm) > self._entry_ladder_order_ttl_s:
                            try:
                                self._call_with_retry(lambda: self.connector.cancel_order(str(txid)), "entry_ladder_cancel_ttl")
                            except Exception:
                                pass
            except Exception:
                pass
        spacing_mult = float(vol_adjust.get("ladder_spacing_mult", 1.0) or 1.0)
        mid = (bid + ask) / 2.0
        prices = self._entry_ladder_prices(pair, mid, spacing_mult)
        if not prices:
            return None
        step_notional = min(float(target_notional), float(quote_usable)) / max(1, len(prices))
        constraints = self.min_guard.constraint_snapshot(pair, ask)
        min_quote = max(0.0, float(constraints.get("min_notional_quote", 0.0) or 0.0))
        if step_notional < min_quote:
            step_notional = min_quote
        submitted: list[dict[str, Any]] = []
        remaining_quote = float(quote_usable)
        for idx, ladder_price in enumerate(prices):
            if remaining_quote < max(min_quote, 1e-9):
                break
            step_quote = min(step_notional, remaining_quote)
            qty = self._round_volume_down_to_step(pair, step_quote / max(ladder_price, 1e-9))
            if qty <= 0.0:
                continue
            notional = qty * ladder_price
            if notional < min_quote:
                continue
            params = {
                "pair": pair,
                "type": "buy",
                "ordertype": "limit",
                "price": f"{ladder_price:.8f}",
                "volume": f"{qty:.8f}",
                "oflags": "post",
                "userref": str((int(userref_seed) + idx) % 2_147_483_647 or 1),
            }
            try:
                out = self._call_with_retry(lambda: self.connector.add_order(params), "entry_ladder_submit")
            except Exception:
                continue
            txids = out.get("txid", []) if isinstance(out, dict) else []
            txid = txids[0] if isinstance(txids, list) and txids else ""
            if txid:
                self._register_order_attempt(pair, txid, "buy", ladder_price, now)
            submitted.append(
                {
                    "txid": txid,
                    "price": ladder_price,
                    "volume": qty,
                    "notional": notional,
                }
            )
            remaining_quote -= notional
        if not submitted:
            return None
        self._entry_ladder_last_submit_ts[pair] = now
        return LiveExecutionResult(
            status="submitted_ladder",
            reason="entry_ladder_submitted",
            order={
                "pair": pair,
                "side": "buy",
                "quote_ccy": quote_ccy,
                "ladder_orders": submitted,
                "ladder_steps_submitted": float(len(submitted)),
                "request_sent": True,
            },
        )

    def _submit_profit_locked_sell(
        self,
        *,
        pair: str,
        vol: float,
        bid: float,
        ask: float,
        base_order: dict[str, Any],
        gate_details: dict[str, Any],
        dedupe: str,
        now: float,
        base_ccy: str,
        slippage_bps: float,
    ) -> LiveExecutionResult:
        floor_price = float(gate_details.get("min_sell_price", 0.0) or 0.0)
        floor_price = self._round_price_up_to_tick(pair, floor_price)
        if floor_price <= 0.0:
            return LiveExecutionResult(
                status="blocked",
                reason="profit_lock_floor_invalid",
                order={"pair": pair, "side": "sell", **gate_details},
            )
        invariant_ok, invariant_reason = self._enforce_sell_profit_invariant(
            pair=pair,
            bid=bid,
            ask=ask,
            qty=vol,
            gate_details=gate_details,
            slippage_bps=slippage_bps,
        )
        if not invariant_ok:
            return LiveExecutionResult(
                status="blocked",
                reason=invariant_reason,
                order={"pair": pair, "side": "sell", **gate_details},
            )
        if time.time() < self.rate_limit_cooldown_until_s:
            return self._rate_limit_cooldown_result({"pair": pair, "stage": "sell_limit_submit"})

        tick = 10 ** (-max(0, int(self.min_guard.pair_meta(pair).get("pair_decimals", 8) or 8)))
        attempt_price = floor_price
        retries = self._sell_post_only_retry_ticks if self._sell_post_only_default else 1
        last_exc: Exception | None = None
        extra_params = {
            k: v
            for k, v in base_order.items()
            if k not in {"pair", "type", "volume", "ordertype", "price"}
        }
        for _ in range(max(1, retries)):
            try:
                out = self.exit_order_manager.submit_sell_limit_floor(
                    pair=pair,
                    qty=vol,
                    floor_price=attempt_price,
                    bid=bid,
                    extra_params=extra_params,
                    stage="sell_limit_submit",
                )
                final_price = max(attempt_price, self._round_price_up_to_tick(pair, bid + tick) if self._sell_post_only_default and attempt_price <= bid else attempt_price)
                txids = out.get("txid", []) if isinstance(out, dict) else []
                txid = txids[0] if isinstance(txids, list) and txids else ""
                self._recent_ids[dedupe] = now
                self._register_order_attempt(pair, txid, "sell", final_price, now)
                return LiveExecutionResult(
                    status="submitted_limit_floor",
                    reason="spot_sell_limit_floor_submitted",
                    order={
                        "pair": pair,
                        "side": "sell",
                        "volume": vol,
                        "price": final_price,
                        "bid": bid,
                        "ask": ask,
                        "min_sell_price": floor_price,
                        "required_exit_price": floor_price,
                        "base_ccy": base_ccy,
                        "txid": txid,
                        "execution_mode": "limit_floor",
                        "execution_mode_reason": "profit_gate_floor",
                        "request_sent": True,
                        **gate_details,
                    },
                )
            except Exception as exc:
                last_exc = exc
                if self._sell_post_only_default and self._is_post_only_reject(exc):
                    attempt_price = self._round_price_up_to_tick(pair, attempt_price + tick)
                    continue
                return self._reject_guard(exc, {"pair": pair, "side": "sell", "stage": "sell_limit_submit", "request_sent": True})
        if last_exc is not None:
            return self._reject_guard(last_exc, {"pair": pair, "side": "sell", "stage": "sell_limit_submit", "request_sent": True})
        return LiveExecutionResult(status="blocked", reason="sell_limit_submit_failed", order={"pair": pair, "side": "sell"})

    def _maybe_reprice_exit_orders(self, pair: str, bid: float, ask: float) -> None:
        now = time.time()
        if now < self.rate_limit_cooldown_until_s:
            return
        _ = self.exit_order_manager.maybe_reprice(
            pair=pair,
            bid=bid,
            ask=ask,
            now_ts=now,
            should_manage_order=lambda descr, sym: (
                str(descr.get("type", "") or "").lower() == "sell"
                and (not str(descr.get("pair", "") or "") or self._trade_matches_pair(str(descr.get("pair", "") or ""), sym))
            ),
            required_floor_price=lambda rem_qty: (
                lambda blocked, details: (
                    (False, 0.0)
                    if blocked
                    else (True, float(details.get("min_sell_price", 0.0) or 0.0))
                )
            )(
                *self._sell_profit_lock_violation(
                    pair=pair,
                    bid=bid,
                    ask=ask,
                    intent=_IntentView(symbol=pair, side="sell", target_notional=rem_qty * bid, why={}),
                    target_exit_qty=rem_qty,
                )
            ),
        )

    def _refresh_fee_profile(self, pair: str | None = None) -> None:
        if not self.connector.has_credentials:
            return
        if not hasattr(self.connector, "trade_volume"):
            return
        try:
            raw = self.connector.trade_volume(pair=pair, fee_info=True)  # type: ignore[attr-defined]
        except Exception:
            return
        if not isinstance(raw, dict):
            return
        fees = raw.get("fees", {})
        if not isinstance(fees, dict) or not fees:
            return
        chosen_fee_pct = None
        if pair and pair in fees and isinstance(fees.get(pair), dict):
            chosen_fee_pct = fees[pair].get("fee")
        if chosen_fee_pct is None:
            first = next(iter(fees.values()))
            if isinstance(first, dict):
                chosen_fee_pct = first.get("fee")
        try:
            fee_pct = float(chosen_fee_pct)
        except Exception:
            return
        # Kraken returns fee in %, e.g. 0.26 means 26 bps.
        taker_fee_bps = max(0.0, fee_pct * 100.0)
        if taker_fee_bps <= 0.0:
            return
        self._entry_fee_bps = max(self._entry_fee_bps, taker_fee_bps)
        self._exit_fee_bps = max(self._exit_fee_bps, taker_fee_bps)
        self.profit_gate.config.default_entry_fee_bps = self._entry_fee_bps
        self.profit_gate.config.default_exit_fee_bps = self._exit_fee_bps
        self._last_fee_refresh_ts = time.time()
        try:
            self._last_trade_volume_hint = max(self._last_trade_volume_hint, float(raw.get("volume", 0.0) or 0.0))
        except Exception:
            pass

    def set_fee_profile(self, profile: Any) -> None:
        if profile is None:
            return
        spot_taker = max(
            0.0,
            float(getattr(profile, "spot_taker_fee_bps", self._exit_fee_bps) or self._exit_fee_bps),
        )
        spot_maker = max(
            0.0,
            float(getattr(profile, "spot_maker_fee_bps", self._entry_fee_bps) or self._entry_fee_bps),
        )
        worst_case = max(spot_taker, spot_maker, self._entry_fee_bps, self._exit_fee_bps)
        self._entry_fee_bps = worst_case
        self._exit_fee_bps = worst_case
        self.profit_gate.config.default_entry_fee_bps = float(worst_case)
        self.profit_gate.config.default_exit_fee_bps = float(worst_case)

    def set_profit_gate_slippage_bps(self, bps: float) -> None:
        val = max(
            self._slippage_calibration_min_bps,
            min(
                self._slippage_calibration_max_bps,
                float(bps),
            ),
        )
        self._slippage_bps_profit_gate = float(val)
        self.profit_gate.config.default_slippage_bps = float(val)

    def _classify_reject(self, exc: Exception | str) -> str:
        text = str(exc).lower()
        if "rate limit" in text or "429" in text or "temporary lockout" in text:
            return "rate_limit"
        if "insufficient funds" in text or "insufficient balance" in text:
            return "insufficient_funds"
        if "post only" in text or "would execute immediately" in text:
            return "post_only_cross"
        if "invalid" in text or "precision" in text or "minimum" in text:
            return "constraints"
        if "unknown asset pair" in text or "asset pair not available" in text or "restricted" in text:
            return "restricted"
        return "other"

    def _apply_reject_remedy(self, *, pair: str, stage: str, category: str) -> None:
        _ = stage
        key = str(pair or "")
        if not key:
            return
        self._pair_reject_counts[key] = int(self._pair_reject_counts.get(key, 0) or 0) + 1
        if category == "rate_limit":
            self._activate_rate_limit_cooldown(multiplier=1.5)
            # Adaptive scheduler/churn under rate-limit storms.
            self._entry_ladder_refresh_s = min(60.0, max(self._entry_ladder_refresh_s, self._entry_ladder_refresh_s * 1.25))
            self.exit_order_manager.config.reprice_interval_s = min(
                120.0,
                max(
                    float(self.exit_order_manager.config.reprice_interval_s),
                    float(self.exit_order_manager.config.reprice_interval_s) * 1.25,
                ),
            )
        elif category == "insufficient_funds":
            # Funding/balance can change quickly; avoid long quarantine on temporary balance rejects.
            self._activate_rate_limit_cooldown(multiplier=1.05)
        elif category in {"constraints", "restricted"}:
            self._quarantine_pair(key, minutes=self._symbol_quarantine_min)
        elif self._pair_reject_counts[key] >= 3:
            self._quarantine_pair(key, minutes=self._symbol_quarantine_min)

    def _taker_fallback_edge_ok(self, intent) -> bool:
        comps = intent.why.get("components", []) if isinstance(intent.why, dict) else []
        if not comps:
            return True
        for c in comps:
            edge = float(c.get("final_edge_bps", c.get("edge_bps", 0.0)))
            cost = float(c.get("cost_total_bps", 0.0))
            if edge > cost:
                return True
        return False

    def _taker_fallback_allowed(self, side: str) -> bool:
        side_norm = str(side).strip().lower()
        if side_norm == "buy":
            return bool(self._taker_fallback_buy_enabled)
        if side_norm == "sell":
            return bool(self._taker_fallback_sell_enabled)
        return bool(self._taker_fallback_enabled)

    def _best_edge_margin_bps(self, intent) -> float:
        comps = intent.why.get("components", []) if isinstance(intent.why, dict) else []
        if not comps:
            return 0.0
        best = -10**9
        for c in comps:
            edge = float(c.get("final_edge_bps", c.get("edge_bps", 0.0)))
            cost = float(c.get("cost_total_bps", 0.0))
            best = max(best, edge - cost)
        return 0.0 if best == -10**9 else best

    def _adaptive_maker_preference(self, intent, side: str, bid: float, ask: float) -> tuple[bool, str]:
        base_pref = bool(self.settings.execution.maker_preference)
        route_hint = intent.why.get("execution_route", {}) if isinstance(intent.why, dict) else {}
        if isinstance(route_hint, dict):
            forced = str(route_hint.get("order_type", "") or "").lower()
            if forced == "maker":
                return True, "router_forced_maker"
            if forced == "taker":
                return False, "router_forced_taker"
        mid = (bid + ask) / 2.0
        spread_bps = ((ask - bid) / max(mid, 1e-9)) * 10000.0
        edge_margin_bps = self._best_edge_margin_bps(intent)
        risk = intent.why.get("risk", {}) if isinstance(intent.why, dict) else {}
        decision_reason = str(risk.get("decision_reason", ""))

        urgent = False
        if side == "sell":
            urgent = any(k in decision_reason for k in ("kill", "flatten", "drawdown", "loss", "cooldown"))
        if urgent:
            return False, "urgent_reduce_only"
        if spread_bps <= 1.0:
            return False, "tight_spread_taker"
        if edge_margin_bps <= 0.0:
            if base_pref:
                return True, "maker_first_edge_probe"
            return False, "edge_le_cost"
        if not base_pref:
            if spread_bps >= 4.0 and edge_margin_bps >= 8.0:
                return True, "adaptive_maker_override"
            return False, "config_taker_bias"
        if spread_bps >= 2.0 and edge_margin_bps >= 1.0:
            return True, "maker_first"
        return False, "adaptive_taker"

    def market_snapshot(self, pair: str, *, max_age_s: float | None = None, force_refresh: bool = False) -> dict[str, Any]:
        now = time.time()
        ttl = self._ticker_ttl_s if max_age_s is None else max(0.05, float(max_age_s))
        cached = self._ticker_cache.get(pair, {})
        if cached and not force_refresh:
            ts = float(cached.get("ts", 0.0) or 0.0)
            if now - ts <= ttl:
                return dict(cached)
        try:
            t = self.connector.ticker(pair)
            row = t.get(pair) if isinstance(t, dict) else None
            if not row and isinstance(t, dict) and t:
                row = next(iter(t.values()))
            if not isinstance(row, dict):
                raise KrakenConnectorError(f"ticker_missing:{pair}")
            bid_raw = row.get("b", 0.0)
            ask_raw = row.get("a", 0.0)
            bid = float(bid_raw[0] if isinstance(bid_raw, list) and bid_raw else bid_raw or 0.0)
            ask = float(ask_raw[0] if isinstance(ask_raw, list) and ask_raw else ask_raw or 0.0)
            bid_qty = float(bid_raw[1] if isinstance(bid_raw, list) and len(bid_raw) > 1 else 0.0)
            ask_qty = float(ask_raw[1] if isinstance(ask_raw, list) and len(ask_raw) > 1 else 0.0)
            if bid <= 0.0 or ask <= 0.0:
                raise KrakenConnectorError(f"ticker_invalid:{pair}")
            out = {
                "pair": pair,
                "bid": bid,
                "ask": ask,
                "bid_qty": bid_qty,
                "ask_qty": ask_qty,
                "mid": (bid + ask) / 2.0,
                "spread_bps": ((ask - bid) / max((bid + ask) / 2.0, 1e-9)) * 10000.0,
                "ts": now,
                "stale": False,
            }
            self._record_midpoint(pair, float(out["mid"]), now)
            self._ticker_cache[pair] = out
            return dict(out)
        except Exception:
            if cached:
                fallback = dict(cached)
                fallback["stale"] = True
                self._record_midpoint(pair, float(fallback.get("mid", 0.0) or 0.0), now)
                return fallback
            raise

    def _balance_snapshot(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now = time.time()
        if now < self._temporary_lockout_until_s:
            if self._balance_cache:
                return dict(self._balance_cache)
            self._balance_cache_ts = now
            return {}
        if self._balance_cache and not force_refresh and (now - self._balance_cache_ts) <= self._balance_ttl_s:
            return dict(self._balance_cache)
        try:
            bal = self.connector.balance()
            self._balance_cache = dict(bal) if isinstance(bal, dict) else {}
            self._balance_cache_ts = now
            return dict(self._balance_cache)
        except Exception as exc:
            if self._is_temporary_lockout_error(exc):
                self._activate_temporary_lockout(now)
                if self._balance_cache:
                    self._balance_cache_ts = now
                    return dict(self._balance_cache)
                self._balance_cache_ts = now
                return {}
            if self._balance_cache:
                return dict(self._balance_cache)
            raise

    def _trades_snapshot(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now = time.time()
        if now < self._temporary_lockout_until_s:
            if self._trades_cache:
                self._trades_cache_ts = now
                return dict(self._trades_cache)
            self._trades_cache_ts = now
            return {}
        if self._trades_cache and not force_refresh and (now - self._trades_cache_ts) <= self._trades_ttl_s:
            return dict(self._trades_cache)
        try:
            trades = self.connector.trades_history()
            self._trades_cache = dict(trades) if isinstance(trades, dict) else {}
            self._trades_cache_ts = now
            return dict(self._trades_cache)
        except Exception as exc:
            if self._is_temporary_lockout_error(exc):
                self._activate_temporary_lockout(now)
                if self._trades_cache:
                    self._trades_cache_ts = now
                    return dict(self._trades_cache)
                self._trades_cache_ts = now
                return {}
            if self._trades_cache:
                self._trades_cache_ts = now
                return dict(self._trades_cache)
            txt = str(exc).lower()
            if (
                self.settings.execution.kraken_spot.allow_unknown_permissions
                and ("permission denied" in txt or "authentication" in txt or "invalid key" in txt)
            ):
                # Trade-history query may be disallowed on constrained keys; keep runtime alive.
                self._trades_cache_ts = now
                return {}
            raise

    def _call_with_retry(self, fn, stage: str):
        attempts = max(1, min(self._exec_retry_attempts, self._endpoint_retry_budget + 1))
        for idx in range(attempts):
            try:
                return fn()
            except Exception as exc:
                if not self._is_rate_limit_err(exc):
                    raise
                now = time.time()
                if self._is_temporary_lockout_error(exc):
                    self._activate_temporary_lockout(now)
                    raise
                hit_count = self._endpoint_rate_limit_count(stage, now)
                cooldown_mult = self._endpoint_retry_backoff_mult ** max(0, hit_count - 1)
                self._activate_rate_limit_cooldown(now, multiplier=cooldown_mult)
                # Adaptive cadence reduction under repeated 429s.
                self.cooldown_until_s = max(self.cooldown_until_s, self.rate_limit_cooldown_until_s)
                if hit_count >= self._endpoint_rate_limit_budget:
                    raise
                if idx >= attempts - 1:
                    raise
                sleep_s = min(
                    self._exec_retry_backoff_max_s,
                    self._exec_retry_backoff_s * (self._endpoint_retry_backoff_mult ** idx),
                )
                time.sleep(max(0.0, float(sleep_s)))
        raise KrakenConnectorError(f"retry_exhausted:{stage}")

    def _ledger_for(self, pair: str) -> FillLedger:
        return self._ledgers.setdefault(pair, FillLedger())

    def _pair_aliases(self, pair: str) -> set[str]:
        aliases = {pair, pair.replace("/", "")}
        meta = self.min_guard.pair_meta(pair)
        for k in ("altname", "wsname"):
            val = str(meta.get(k, "") or "")
            if val:
                aliases.add(val)
                aliases.add(val.replace("/", ""))
        return {a for a in aliases if a}

    def _trade_matches_pair(self, trade_pair: str, target_pair: str) -> bool:
        if not trade_pair:
            return False
        trade_norm = trade_pair.replace("/", "")
        if trade_pair in self._pair_aliases(target_pair) or trade_norm in self._pair_aliases(target_pair):
            return True
        t_meta = self.min_guard.pair_meta(trade_pair)
        x_meta = self.min_guard.pair_meta(target_pair)
        if not t_meta or not x_meta:
            return False
        return str(t_meta.get("base", "")) == str(x_meta.get("base", "")) and str(t_meta.get("quote", "")) == str(x_meta.get("quote", ""))

    def _quantile(self, values: list[float], q: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(max(0, min(len(sorted_vals) - 1, round((len(sorted_vals) - 1) * q))))
        return float(sorted_vals[idx])

    def _register_order_attempt(self, pair: str, txid: str, side: str, ref_price: float, submit_ts: float) -> None:
        if not txid:
            return
        ledger = self._ledger_for(pair)
        ledger.order_attempts += 1
        self._order_meta[txid] = {
            "pair": pair,
            "side": side,
            "ref_price": float(ref_price),
            "submit_ts": float(submit_ts),
            "filled": False,
        }

    def _record_execution_qa_from_trade(self, ledger: FillLedger, trade: dict[str, Any]) -> None:
        txid = str(trade.get("ordertxid", "") or "")
        if not txid:
            return
        meta = self._order_meta.get(txid)
        if not meta:
            return
        trade_price = float(trade.get("price", 0.0) or 0.0)
        ref_price = float(meta.get("ref_price", 0.0) or 0.0)
        trade_side = str(trade.get("type", "") or "").lower()
        if trade_price > 0 and ref_price > 0:
            if trade_side == "buy":
                shortfall_bps = ((trade_price - ref_price) / ref_price) * 10000.0
            else:
                shortfall_bps = ((ref_price - trade_price) / ref_price) * 10000.0
            ledger.shortfall_bps.append(shortfall_bps)
            ledger.shortfall_bps = ledger.shortfall_bps[-2000:]
        t = float(trade.get("time", 0.0) or 0.0)
        submit_ts = float(meta.get("submit_ts", t) or t)
        latency_ms = max(0.0, (t - submit_ts) * 1000.0)
        ledger.latencies_ms.append(latency_ms)
        ledger.latencies_ms = ledger.latencies_ms[-2000:]
        if latency_ms < 250.0:
            ledger.latency_fast += 1
        elif latency_ms < 1000.0:
            ledger.latency_medium += 1
        else:
            ledger.latency_slow += 1
        if not bool(meta.get("filled", False)):
            meta["filled"] = True
            ledger.order_fills += 1
        self._order_meta[txid] = meta

    def _apply_trade_fill(self, pair: str, ledger: FillLedger, trade_id: str, trade: dict[str, Any]) -> None:
        side = str(trade.get("type", "") or "").lower()
        vol = float(trade.get("vol", 0.0) or 0.0)
        price = float(trade.get("price", 0.0) or 0.0)
        fee = float(trade.get("fee", 0.0) or 0.0)
        trade_ts = float(trade.get("time", 0.0) or 0.0)
        if side not in {"buy", "sell"} or vol <= 0.0 or price <= 0.0:
            ledger.trade_ids.add(trade_id)
            return

        if side == "buy":
            ledger.lots.append(
                PositionLot(
                    qty=float(vol),
                    entry_price=float(price),
                    entry_fee_quote=max(0.0, float(fee)),
                    funding_quote=0.0,
                    interest_quote=0.0,
                    opened_ts=trade_ts if trade_ts > 0.0 else time.time(),
                )
            )
        else:
            if not ledger.lots and ledger.position_qty > 1e-12 and ledger.avg_entry_price > 0.0:
                # Compatibility path for legacy snapshots that only had avg-entry state.
                ledger.lots.append(
                    PositionLot(
                        qty=float(ledger.position_qty),
                        entry_price=float(ledger.avg_entry_price),
                        entry_fee_quote=0.0,
                        funding_quote=0.0,
                        interest_quote=0.0,
                        opened_ts=ledger.position_open_ts,
                    )
                )
            # Post-fill invariant check: exchange-reported SELL fills must still satisfy ProfitGate >= +2% net.
            pre_close_lots = [
                PositionLot(
                    qty=float(l.qty),
                    entry_price=float(l.entry_price),
                    entry_fee_quote=float(l.entry_fee_quote),
                    funding_quote=float(l.funding_quote),
                    interest_quote=float(l.interest_quote),
                    opened_ts=l.opened_ts,
                )
                for l in ledger.lots
                if float(l.qty) > 0.0
            ]
            total_qty = sum(max(0.0, float(l.qty)) for l in ledger.lots)
            close_qty = min(max(0.0, float(vol)), total_qty)
            if close_qty > 0.0 and pre_close_lots:
                meta = self.min_guard.pair_meta(pair)
                pair_decimals = int(meta.get("pair_decimals", 8) or 8)
                tick_size = 10 ** (-max(0, pair_decimals))
                decision = self.profit_gate.can_close_long(
                    lots=pre_close_lots,
                    exit_price=float(price),
                    exit_qty=float(close_qty),
                    tick_size=tick_size,
                    entry_fee_bps=self._entry_fee_bps,
                    exit_fee_bps=self._exit_fee_bps,
                    slippage_bps=self._slippage_bps_profit_gate,
                    accounting_method=self._position_accounting_method,
                )
                if not bool(decision.allowed):
                    self.safe_mode = True
                    self.kill_reason = "post_fill_sell_invariant_violation"
                    self.cooldown_until_s = max(
                        self.cooldown_until_s,
                        time.time() + max(60.0, self._auto_recover_kill_min_cooldown_s),
                    )
            if close_qty > 0.0:
                if self._position_accounting_method == "average":
                    denom = max(total_qty, 1e-9)
                    ratio = min(1.0, close_qty / denom)
                    new_lots: list[PositionLot] = []
                    for lot in ledger.lots:
                        lot_qty = max(0.0, float(lot.qty))
                        if lot_qty <= 0.0:
                            continue
                        take = lot_qty * ratio
                        ledger.realized_gross_quote += (price - float(lot.entry_price)) * take
                        rem_qty = lot_qty - take
                        if rem_qty > 1e-12:
                            rem_ratio = rem_qty / lot_qty
                            new_lots.append(
                                PositionLot(
                                    qty=rem_qty,
                                    entry_price=float(lot.entry_price),
                                    entry_fee_quote=float(lot.entry_fee_quote) * rem_ratio,
                                    funding_quote=float(lot.funding_quote) * rem_ratio,
                                    interest_quote=float(lot.interest_quote) * rem_ratio,
                                    opened_ts=lot.opened_ts,
                                )
                            )
                    ledger.lots = new_lots
                else:
                    rem = close_qty
                    new_lots = []
                    for lot in ledger.lots:
                        lot_qty = max(0.0, float(lot.qty))
                        if lot_qty <= 0.0:
                            continue
                        if rem <= 1e-12:
                            new_lots.append(lot)
                            continue
                        take = min(rem, lot_qty)
                        ledger.realized_gross_quote += (price - float(lot.entry_price)) * take
                        rem_qty = lot_qty - take
                        if rem_qty > 1e-12:
                            rem_ratio = rem_qty / lot_qty
                            new_lots.append(
                                PositionLot(
                                    qty=rem_qty,
                                    entry_price=float(lot.entry_price),
                                    entry_fee_quote=float(lot.entry_fee_quote) * rem_ratio,
                                    funding_quote=float(lot.funding_quote) * rem_ratio,
                                    interest_quote=float(lot.interest_quote) * rem_ratio,
                                    opened_ts=lot.opened_ts,
                                )
                            )
                        rem -= take
                    ledger.lots = new_lots

        ledger.fees_quote += fee
        ledger.filled_notional_quote += vol * price
        ledger.fill_events += 1
        ledger.position_qty = sum(max(0.0, float(l.qty)) for l in ledger.lots)
        if ledger.position_qty > 1e-12:
            weighted_entry = sum(float(l.entry_price) * float(l.qty) for l in ledger.lots)
            ledger.avg_entry_price = weighted_entry / max(ledger.position_qty, 1e-9)
            if ledger.position_open_ts is None:
                ledger.position_open_ts = trade_ts if trade_ts > 0.0 else time.time()
        else:
            ledger.avg_entry_price = 0.0
            ledger.position_open_ts = None
        ledger.trade_ids.add(trade_id)
        self._record_execution_qa_from_trade(ledger, trade)

    def _ledger_snapshot(self, pair: str, mark_price: float) -> dict[str, Any]:
        ledger = self._ledger_for(pair)
        self._maybe_bootstrap_ledger_position(pair, ledger, mark_price)
        position_age_s = 0.0
        if ledger.position_open_ts is not None:
            position_age_s = max(0.0, time.time() - float(ledger.position_open_ts))
        mark = max(0.0, float(mark_price))
        signed_notional = ledger.position_qty * mark
        unrealized_quote = (mark - ledger.avg_entry_price) * ledger.position_qty if ledger.position_qty > 0.0 else 0.0
        net_quote = ledger.realized_gross_quote + unrealized_quote - ledger.fees_quote
        fill_probability = 0.0 if ledger.order_attempts <= 0 else (ledger.order_fills + 1.0) / (ledger.order_attempts + 2.0)
        avg_shortfall = 0.0 if not ledger.shortfall_bps else sum(ledger.shortfall_bps) / len(ledger.shortfall_bps)
        qa = {
            "implementation_shortfall_bps": avg_shortfall,
            "latency_p50_ms": self._quantile(ledger.latencies_ms, 0.5),
            "latency_p95_ms": self._quantile(ledger.latencies_ms, 0.95),
            "latency_bucket_fast": float(ledger.latency_fast),
            "latency_bucket_medium": float(ledger.latency_medium),
            "latency_bucket_slow": float(ledger.latency_slow),
            "fill_probability": fill_probability,
            "orders_attempted": float(ledger.order_attempts),
            "orders_filled": float(ledger.order_fills),
        }
        meta = self.min_guard.pair_meta(pair)
        costmin = float(meta.get("costmin", 0.0) or 0.0)
        ordermin = float(meta.get("ordermin", 0.0) or 0.0)
        min_trade_notional = max(costmin, ordermin * mark)
        return {
            "pair": pair,
            "position_qty": ledger.position_qty,
            "position_lot_count": float(len(ledger.lots)),
            "position_notional_signed": signed_notional,
            "exposure_notional": abs(signed_notional),
            "avg_entry_price": ledger.avg_entry_price,
            "position_age_s": position_age_s,
            "realized_gross_quote": ledger.realized_gross_quote,
            "fees_quote": ledger.fees_quote,
            "filled_notional_quote": ledger.filled_notional_quote,
            "unrealized_pnl_quote": unrealized_quote,
            "net_pnl_after_fees_quote": net_quote,
            "min_trade_notional_quote": min_trade_notional,
            "execution_qa": qa,
        }

    def _maybe_bootstrap_ledger_position(self, pair: str, ledger: FillLedger, mark_price: float) -> None:
        if not self._bootstrap_balance_position:
            return
        if ledger.bootstrapped_from_balance:
            return
        if ledger.trade_ids or abs(ledger.position_qty) > 1e-12:
            ledger.bootstrapped_from_balance = True
            return
        _base_ccy, available_base = self._available_base_balance(pair)
        if self._bootstrap_require_tradeable:
            meta = self.min_guard.pair_meta(pair)
            ordermin = float(meta.get("ordermin", 0.0) or 0.0)
            if ordermin > 0.0 and available_base < ordermin:
                ledger.bootstrapped_from_balance = True
                return
        if available_base > 0.0:
            ledger.position_qty = float(available_base)
            # Start from neutral mark so bootstrap does not fabricate initial pnl.
            ledger.avg_entry_price = max(0.0, float(mark_price))
            ledger.position_open_ts = time.time()
            ledger.lots = [
                PositionLot(
                    qty=float(ledger.position_qty),
                    entry_price=float(ledger.avg_entry_price),
                    entry_fee_quote=0.0,
                    funding_quote=0.0,
                    interest_quote=0.0,
                    opened_ts=ledger.position_open_ts,
                )
            ]
        else:
            ledger.position_open_ts = None
            ledger.lots = []
        ledger.bootstrapped_from_balance = True

    def sync_fill_ledger(self, pair: str, mark_price: float) -> dict[str, Any]:
        ledger = self._ledger_for(pair)
        now = time.time()
        if now < self._temporary_lockout_until_s:
            self._last_ledger_sync_ts[pair] = now
            return self._ledger_snapshot(pair, mark_price)
        last_sync = self._last_ledger_sync_ts.get(pair, 0.0)
        if now - last_sync < self._trades_sync_min_interval_s:
            return self._ledger_snapshot(pair, mark_price)
        self._last_ledger_sync_ts[pair] = now
        trades = self._trades_snapshot(force_refresh=True)
        if isinstance(trades, dict):
            trade_rows = trades.get("trades", trades)
            pending: list[tuple[float, str, dict[str, Any]]] = []
            for trade_id, trade_row in trade_rows.items() if isinstance(trade_rows, dict) else []:
                if not isinstance(trade_row, dict):
                    continue
                ts = float(trade_row.get("time", 0.0) or 0.0)
                if ts < self._trades_history_since_ts:
                    continue
                tid = str(trade_id)
                if tid in ledger.trade_ids:
                    continue
                trade_pair = str(trade_row.get("pair", "") or "")
                if not self._trade_matches_pair(trade_pair, pair):
                    continue
                pending.append((ts, tid, trade_row))
            pending.sort(key=lambda x: x[0])
            for _ts, tid, row in pending:
                self._apply_trade_fill(pair, ledger, tid, row)
        return self._ledger_snapshot(pair, mark_price)

    def live_state_snapshot(self, pair: str, mark_price: float) -> dict[str, Any]:
        return self.sync_fill_ledger(pair, mark_price)

    def _evict_recent(self, now: float) -> None:
        for k, t in list(self._recent_ids.items()):
            if now - t > self._recent_ttl_s:
                del self._recent_ids[k]

    def _intent_key(self, intent) -> str:
        payload = f"{self.run_id}|{intent.symbol}|{intent.side}|{round(float(intent.target_notional), 6)}|{int(time.time()//5)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _is_fatal_reduce_intent(self, intent) -> bool:
        # Fatal pathways must never bypass ProfitGate for SELL/CLOSE actions.
        _ = intent
        return False

    def _sell_profit_lock_violation(
        self,
        *,
        pair: str,
        bid: float,
        ask: float,
        intent,
        target_exit_qty: float | None = None,
        slippage_bps_override: float | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not self._sell_profit_lock_enabled:
            return False, {}
        # Absolute rule: fatal intents must never bypass ProfitGate.
        mark_price = (bid + ask) / 2.0 if bid > 0.0 and ask > 0.0 else max(bid, ask, 0.0)
        if mark_price > 0.0:
            try:
                self.sync_fill_ledger(pair, mark_price=mark_price)
            except Exception:
                pass
        ledger = self._ledger_for(pair)
        if ledger.position_qty <= 0.0:
            return False, {}
        position_age_s = 0.0
        if ledger.position_open_ts is not None:
            position_age_s = max(0.0, time.time() - float(ledger.position_open_ts))
        legacy_required_profit_bps = (
            self._sell_profit_lock_target_bps
            if position_age_s < self._sell_profit_lock_target_hold_s
            else self._sell_profit_lock_min_bps
        )
        floor_tp_pct, desired_tp_pct_val, peak_profit_pct = self._desired_tp_pct_for_sell(
            pair=pair,
            hold_s=position_age_s,
            avg_entry_price=float(ledger.avg_entry_price),
            bid=float(bid),
            intent=intent,
        )
        required_profit_bps = max(float(legacy_required_profit_bps), float(desired_tp_pct_val) * 100.0)
        required_profit_ratio = max(float(self._profit_target_net), required_profit_bps / 10000.0)
        modeled_tco_bps = max(
            0.0,
            (2.0 * float(self._entry_fee_bps))
            + (2.0 * float(self._slippage_bps_profit_gate))
            + max(0.0, ((ask - bid) / max((ask + bid) / 2.0, 1e-12)) * 10000.0 if ask > 0.0 and bid > 0.0 else 0.0),
        )
        if bool(self._tp_ladder_cfg.enabled) and bool(self._tp_ladder_cfg.after_costs):
            required_profit_ratio = required_profit_ratio + (modeled_tco_bps / 10000.0)
        required_profit_bps_effective = required_profit_ratio * 10000.0
        if ledger.avg_entry_price <= 0.0:
            if not self._sell_profit_lock_require_cost_basis:
                return False, {}
            return True, {
                "position_qty": ledger.position_qty,
                "bid": bid,
                "ask": ask,
                "required_profit_bps": required_profit_bps,
                "required_profit_bps_effective": required_profit_bps_effective,
                "required_net_profit_ratio": required_profit_ratio,
                "tp_ladder_floor_pct": floor_tp_pct,
                "tp_ladder_desired_pct": desired_tp_pct_val,
                "tp_ladder_peak_profit_pct": peak_profit_pct,
                "position_age_s": position_age_s,
                "target_profit_bps": self._sell_profit_lock_target_bps,
                "target_hold_s": self._sell_profit_lock_target_hold_s,
                "min_profit_bps": self._sell_profit_lock_min_bps,
                "profit_lock_reason": "missing_cost_basis",
            }
        # By default require known trade history after restarts to avoid selling unknown inventory at a loss.
        if ledger.bootstrapped_from_balance and not ledger.trade_ids:
            if not self._sell_profit_lock_require_cost_basis:
                return False, {}
            return True, {
                "avg_entry_price": ledger.avg_entry_price,
                "position_qty": ledger.position_qty,
                "bid": bid,
                "ask": ask,
                "required_profit_bps": required_profit_bps,
                "required_profit_bps_effective": required_profit_bps_effective,
                "required_net_profit_ratio": required_profit_ratio,
                "tp_ladder_floor_pct": floor_tp_pct,
                "tp_ladder_desired_pct": desired_tp_pct_val,
                "tp_ladder_peak_profit_pct": peak_profit_pct,
                "position_age_s": position_age_s,
                "target_profit_bps": self._sell_profit_lock_target_bps,
                "target_hold_s": self._sell_profit_lock_target_hold_s,
                "min_profit_bps": self._sell_profit_lock_min_bps,
                "profit_lock_reason": "bootstrapped_without_trade_history",
            }
        if bid <= 0.0:
            return False, {}
        meta = self.min_guard.pair_meta(pair)
        pair_decimals = int(meta.get("pair_decimals", 8) or 8)
        tick_size = 10 ** (-max(0, pair_decimals))

        lots = list(ledger.lots)
        if (not lots) and ledger.position_qty > 1e-12 and ledger.avg_entry_price > 0.0:
            lots = [
                PositionLot(
                    qty=float(ledger.position_qty),
                    entry_price=float(ledger.avg_entry_price),
                    entry_fee_quote=0.0,
                    funding_quote=0.0,
                    interest_quote=0.0,
                    opened_ts=ledger.position_open_ts,
                )
            ]

        desired_qty = float(target_exit_qty) if target_exit_qty is not None else float(ledger.position_qty)
        desired_qty = max(0.0, min(float(ledger.position_qty), desired_qty))
        if desired_qty <= 0.0:
            desired_qty = float(ledger.position_qty)

        gate = self.profit_gate.can_close_long(
            lots=lots,
            exit_price=bid,
            exit_qty=desired_qty,
            tick_size=tick_size,
            min_profit_ratio=required_profit_ratio,
            entry_fee_bps=self._entry_fee_bps,
            exit_fee_bps=self._exit_fee_bps,
            slippage_bps=max(0.1, float(slippage_bps_override if slippage_bps_override is not None else self._slippage_bps_profit_gate)),
            accounting_method=self._position_accounting_method,
        )
        details: dict[str, Any] = {
            "avg_entry_price": ledger.avg_entry_price,
            "position_qty": ledger.position_qty,
            "bid": bid,
            "ask": ask,
            "min_sell_price": gate.required_exit_price,
            "required_profit_bps": required_profit_bps,
            "required_profit_bps_effective": required_profit_bps_effective,
            "required_net_profit_ratio": required_profit_ratio,
            "tp_ladder_floor_pct": floor_tp_pct,
            "tp_ladder_desired_pct": desired_tp_pct_val,
            "tp_ladder_peak_profit_pct": peak_profit_pct,
            "modeled_tco_bps": modeled_tco_bps,
            "position_age_s": position_age_s,
            "target_profit_bps": self._sell_profit_lock_target_bps,
            "target_hold_s": self._sell_profit_lock_target_hold_s,
            "min_profit_bps": self._sell_profit_lock_min_bps,
            "matched_qty": gate.matched_qty,
            "eligible_qty": gate.eligible_qty,
        }
        if gate.allowed:
            return False, details
        if gate.eligible_qty > 0.0:
            details["profit_lock_partial_reduce"] = True
            return False, details
        return True, details

    def _is_temporary_lockout_error(self, exc: Exception | str) -> bool:
        text = str(exc).lower()
        return "temporary lockout" in text

    def _is_rate_limit_err(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            isinstance(exc, KrakenRateLimitError)
            or "rate limit" in text
            or "429" in text
            or self._is_exchange_rate_limit_exceeded(exc)
            or self._is_temporary_lockout_error(exc)
        )

    def _is_exchange_rate_limit_exceeded(self, exc: Exception | str) -> bool:
        text = str(exc).lower()
        return ("eapi:rate limit exceeded" in text) or ("temporary lockout" in text)

    def _is_exchange_restriction_error(self, exc: Exception | str) -> bool:
        text = str(exc).lower()
        return ("restricted" in text) or ("asset pair not available" in text) or ("unknown asset pair" in text)

    def _activate_rate_limit_cooldown(self, now: float | None = None, *, multiplier: float = 1.0) -> None:
        ts = time.time() if now is None else float(now)
        factor = max(1.0, float(multiplier))
        cooldown_s = max(self._rate_limit_cooldown_s, self._rate_limit_cooldown_s * factor)
        self.rate_limit_cooldown_until_s = max(self.rate_limit_cooldown_until_s, ts + cooldown_s)
        self.cooldown_until_s = max(self.cooldown_until_s, self.rate_limit_cooldown_until_s)
        # Adaptive anti-churn behavior during rate-limit storms.
        self._entry_ladder_refresh_s = min(60.0, max(self._entry_ladder_refresh_s, self._entry_ladder_refresh_s * 1.15))
        self.exit_order_manager.config.reprice_interval_s = min(
            180.0,
            max(
                float(self.exit_order_manager.config.reprice_interval_s),
                float(self.exit_order_manager.config.reprice_interval_s) * 1.15,
            ),
        )

    def _activate_temporary_lockout(self, now: float | None = None) -> None:
        ts = time.time() if now is None else float(now)
        self._temporary_lockout_until_s = max(self._temporary_lockout_until_s, ts + self._temporary_lockout_cooldown_s)
        cooldown_mult = max(1.0, self._temporary_lockout_cooldown_s / max(self._rate_limit_cooldown_s, 1e-9))
        self._activate_rate_limit_cooldown(ts, multiplier=cooldown_mult)

    def _rate_limit_cooldown_result(self, order_meta: dict[str, Any] | None = None) -> LiveExecutionResult:
        now = time.time()
        order: dict[str, Any] = dict(order_meta or {})
        order["cooldown_until_s"] = float(self.rate_limit_cooldown_until_s)
        order["cooldown_remaining_s"] = max(0.0, float(self.rate_limit_cooldown_until_s) - now)
        return LiveExecutionResult(status="blocked", reason="rate_limit_cooldown", order=order)

    def _reject_guard(self, exc: Exception, order_meta: dict[str, Any] | None = None) -> LiveExecutionResult:
        now = time.time()
        meta = dict(order_meta or {})
        pair = str(meta.get("pair", "") or "")
        stage = str(meta.get("stage", "") or "")
        category = self._classify_reject(exc)
        if pair:
            self._apply_reject_remedy(pair=pair, stage=stage, category=category)
        if self._is_exchange_restriction_error(exc):
            meta["error"] = str(exc)
            return LiveExecutionResult(status="rejected", reason="restricted_instrument_hard_reject", order=meta)
        if self._is_temporary_lockout_error(exc):
            self._activate_temporary_lockout(now)
            self.rate_limits.add(now)
            meta["error"] = str(exc)
            meta["reject_category"] = "rate_limit"
            meta["temporary_lockout"] = True
            return self._rate_limit_cooldown_result(meta)
        if self._is_rate_limit_err(exc):
            self._activate_rate_limit_cooldown(now)
            self.rate_limits.add(now)
            meta["error"] = str(exc)
            meta["reject_category"] = category
            return self._rate_limit_cooldown_result(meta)
        self.rejects.add(now)
        if self.rejects.storm(self._max_consecutive_rejects):
            if pair:
                self._quarantine_pair(
                    pair,
                    minutes=max(1, int(math.ceil(self._reject_cooldown_s / 60.0))),
                )
            self._activate_rate_limit_cooldown(now, multiplier=max(1.0, self._reject_cooldown_s / max(self._rate_limit_cooldown_s, 1e-9)))
            meta["reject_storm"] = True
            meta["reject_cooldown_s"] = float(self._reject_cooldown_s)
            meta["reject_category"] = category
            return LiveExecutionResult(status="blocked", reason="reject_storm_cooldown", order=meta)
        meta["reject_category"] = category
        return LiveExecutionResult(status="rejected", reason=str(exc), order=meta)

    def _ticker_row(self, symbol: str) -> dict[str, Any]:
        snap = self.market_snapshot(symbol)
        return {"a": [snap.get("ask", 0.0)], "b": [snap.get("bid", 0.0)]}

    def _best_ask(self, symbol: str) -> float:
        row = self._ticker_row(symbol)
        ask = row.get("a", 0.0)
        if isinstance(ask, list):
            ask = ask[0] if ask else 0.0
        return float(ask or 0.0)

    def _best_bid(self, symbol: str) -> float:
        row = self._ticker_row(symbol)
        bid = row.get("b", 0.0)
        if isinstance(bid, list):
            bid = bid[0] if bid else 0.0
        return float(bid or 0.0)

    def _available_quote_balance(self, pair: str) -> tuple[str, float]:
        bal = self._balance_snapshot()
        if not isinstance(bal, dict):
            return ("ZUSD", 0.0)
        meta = self.min_guard.pair_meta(pair)
        quote = str(meta.get("quote", ""))
        candidates: list[str] = []
        if quote:
            candidates.append(quote)
            if quote.startswith("X") or quote.startswith("Z"):
                candidates.append(quote[1:])
        candidates.extend(["ZUSD", "USD", "USDT", "ZEUR", "EUR"])
        seen = set()
        ordered = [k for k in candidates if k and not (k in seen or seen.add(k))]
        for k in ordered:
            if k in bal:
                try:
                    return (k, float(bal.get(k) or 0.0))
                except Exception:
                    return (k, 0.0)
        return ("ZUSD", 0.0)

    def _available_base_balance(self, pair: str, *, force_refresh: bool = False) -> tuple[str, float]:
        bal = self._balance_snapshot(force_refresh=force_refresh)
        if not isinstance(bal, dict):
            return ("", 0.0)
        meta = self.min_guard.pair_meta(pair)
        base = str(meta.get("base", ""))
        if self._is_asset_dust_ignored(base):
            return (base, 0.0)
        candidates = [base]
        if base.startswith("X") or base.startswith("Z"):
            candidates.append(base[1:])
        for k in candidates:
            if not k:
                continue
            if self._is_asset_dust_ignored(k):
                continue
            if k in bal:
                try:
                    return (k, float(bal.get(k) or 0.0))
                except Exception:
                    return (k, 0.0)
        return (base, 0.0)

    def _pretrade_guard(
        self,
        *,
        pair: str,
        side: str,
        target_notional: float,
        reference_price: float,
        available_quote: float,
        available_base: float,
    ) -> tuple[bool, str]:
        ledger = self._ledger_for(pair)
        max_pos = float(getattr(self.settings.risk, "max_position_notional", 0.0) or 0.0)
        max_exp = float(getattr(self.settings.risk, "max_exposure_notional", 0.0) or 0.0)
        if max_pos > 0.0 and target_notional > max_pos * 1.05:
            return False, "pretrade_max_position_notional"
        signed_now = ledger.position_qty * max(reference_price, 0.0)
        projected = signed_now + (target_notional if side == "buy" else -target_notional)
        if max_exp > 0.0 and abs(projected) > max_exp * 1.05:
            return False, "pretrade_exposure_notional"
        if side == "buy" and target_notional > max(0.0, available_quote) * 1.001:
            return False, "pretrade_credit_insufficient_quote"
        if side == "sell" and target_notional > max(0.0, available_base) * max(reference_price, 0.0) * 1.001:
            return False, "pretrade_credit_insufficient_base"
        return True, "ok"

    def preflight(self) -> tuple[bool, str]:
        if self.settings.execution_mode_enum() == ExecutionMode.LIVE_READONLY:
            return True, "readonly"
        ok_perm, reason_perm = self.connector.verify_live_permissions()
        if not ok_perm:
            return False, reason_perm
        if "kraken_spot" not in self.settings.provider_whitelist:
            return False, "provider_not_whitelisted"
        if not self.connector.has_credentials:
            return False, "missing_credentials"
        return True, "ok"

    def execute_readonly(self, intent) -> LiveExecutionResult:
        symbol = intent.symbol
        snap = self.market_snapshot(symbol, max_age_s=max(self._ticker_ttl_s, 1.0), force_refresh=True)
        return LiveExecutionResult(status="readonly_preview", order={"symbol": symbol, "ticker": snap, "target_notional": getattr(intent, "target_notional", 0.0)})

    def execute_intent(self, intent) -> LiveExecutionResult:
        now = time.time()
        if self.killed or self.safe_mode:
            if (
                self._auto_recover_kill_enabled
                and now >= float(self.cooldown_until_s or 0.0)
                and str(self.kill_reason or "").strip().lower() not in {"operator_kill", "manual"}
            ):
                self.killed = False
                self.safe_mode = False
                self.kill_reason = ""
            else:
                if self.killed:
                    return LiveExecutionResult(status="killed", reason=self.kill_reason or "kill_switch_active")
                return LiveExecutionResult(status="blocked", reason="safe_mode")
        if now < self.rate_limit_cooldown_until_s:
            return self._rate_limit_cooldown_result({"pair": str(getattr(intent, "symbol", ""))})
        if now < self.cooldown_until_s:
            return LiveExecutionResult(status="blocked", reason="cooldown")

        side = str(intent.side).lower()
        if side not in {"buy", "sell"}:
            return LiveExecutionResult(status="blocked", reason="invalid_side")

        dedupe = self._intent_key(intent)
        self._evict_recent(now)
        if dedupe in self._recent_ids:
            return LiveExecutionResult(status="deduped", reason="intent_dedupe", order={"intent_id": dedupe})

        pair = intent.symbol
        why_raw = getattr(intent, "why", {})
        why = dict(why_raw) if isinstance(why_raw, Mapping) else {}
        is_probe = bool(why.get("scheduler_probe", False))
        self._maybe_refresh_fee_profile(pair=pair)
        self._maybe_calibrate_slippage(now)
        if side == "buy" and self._entry_block_active(now):
            self._record_probe_result(is_probe=is_probe, success=False, reason="entries_blocked_until_health_ok")
            return LiveExecutionResult(
                status="blocked",
                reason="entries_blocked_until_health_ok",
                order={
                    "pair": pair,
                    "side": side,
                    "entry_block_until_s": float(self._entries_blocked_until_ts or 0.0),
                    "entry_block_remaining_s": max(0.0, float(self._entries_blocked_until_ts or 0.0) - now),
                },
            )
        if side == "buy" and self._is_pair_quarantined(pair):
            self._record_probe_result(is_probe=is_probe, success=False, reason="symbol_quarantine")
            return LiveExecutionResult(status="blocked", reason="symbol_quarantine", order={"pair": pair, "side": side})
        if side == "buy" and time.time() < self._exits_only_mode_until_s:
            self._record_probe_result(is_probe=is_probe, success=False, reason="exits_only_mode")
            return LiveExecutionResult(
                status="blocked",
                reason="exits_only_mode",
                order={
                    "pair": pair,
                    "side": side,
                    "exits_only_reason": self._exits_only_reason,
                    "exits_only_until_s": float(self._exits_only_mode_until_s),
                },
            )
        if side == "buy" and self._session_adapter_enabled:
            session_ok, session_reason = self._session_adapter.is_open(pair, ts=now)
            if not session_ok:
                self._record_probe_result(is_probe=is_probe, success=False, reason="session_closed")
                return LiveExecutionResult(status="blocked", reason="session_closed", order={"pair": pair, "side": side, "session_reason": session_reason})
        market_hint = why.get("market_snapshot", {}) if isinstance(why, dict) else {}
        gate_details_for_sell: dict[str, Any] = {}
        vol_adjust = self._volatility_adjustments(pair)
        slippage_for_gate = max(
            0.1,
            float(self._slippage_bps_profit_gate) * float(vol_adjust.get("slippage_mult", 1.0) or 1.0),
        )
        try:
            snap: dict[str, Any] = {}
            if isinstance(market_hint, dict):
                bid_hint = float(market_hint.get("bid", 0.0) or 0.0)
                ask_hint = float(market_hint.get("ask", 0.0) or 0.0)
                if bid_hint > 0.0 and ask_hint > 0.0:
                    snap = dict(market_hint)
                    snap.setdefault("stale", False)
                    snap.setdefault("bid_qty", 0.0)
                    snap.setdefault("ask_qty", 0.0)
                    snap.setdefault("ts", now)
            if not snap:
                snap = self.market_snapshot(pair, max_age_s=max(self._ticker_ttl_s, 0.5))
            bid = float(snap.get("bid", 0.0) or 0.0)
            ask = float(snap.get("ask", 0.0) or 0.0)
            bid_qty = float(snap.get("bid_qty", 0.0) or 0.0)
            ask_qty = float(snap.get("ask_qty", 0.0) or 0.0)
            spread_bps = float(snap.get("spread_bps", 0.0) or 0.0)
            market_is_stale = bool(snap.get("stale", False))
            self._record_midpoint(pair, (bid + ask) / 2.0 if bid > 0.0 and ask > 0.0 else 0.0, float(snap.get("ts", now) or now))
            if ask <= 0 or bid <= 0:
                return LiveExecutionResult(status="blocked", reason="invalid_book")
            if side == "sell" and market_is_stale and self._stale_sell_block:
                return LiveExecutionResult(
                    status="blocked",
                    reason="stale_market_data_sell_block",
                    order={"pair": pair, "side": side, "stale": True},
                )
            if side == "buy" and market_is_stale and self._safe_mode_block_stale_buy:
                return LiveExecutionResult(
                    status="blocked",
                    reason="stale_market_data_buy_block",
                    order={"pair": pair, "side": side, "stale": True},
                )
            self._maybe_hourly_pnl_reconcile(pair=pair, mark_price=((bid + ask) / 2.0))
            self._maybe_reprice_exit_orders(pair, bid, ask)
            quote_ccy, available_quote = self._available_quote_balance(pair)
            base_ccy, available_base = self._available_base_balance(pair, force_refresh=(side == "sell"))
            self._maybe_balance_drift_refresh(pair=pair, available_base=available_base, mark_price=((bid + ask) / 2.0))
            micro = self._microstructure_metrics(bid, ask, bid_qty, ask_qty)
            if side == "buy":
                ob_ok, ob_reason = self._orderbook_sanity_for_entry(
                    bid=bid,
                    ask=ask,
                    bid_qty=bid_qty,
                    ask_qty=ask_qty,
                    spread_bps=spread_bps,
                )
                if not ob_ok:
                    self._quarantine_pair(pair, minutes=max(2, self._symbol_quarantine_min // 2))
                    return LiveExecutionResult(
                        status="blocked",
                        reason=ob_reason,
                        order={"pair": pair, "side": side, "bid": bid, "ask": ask, "bid_qty": bid_qty, "ask_qty": ask_qty, "spread_bps": spread_bps},
                    )
                if self._no_trade_zone_enabled and (
                    spread_bps > self._no_trade_zone_spread_bps
                    or min(bid_qty, ask_qty) < self._no_trade_zone_min_top_qty
                    or min(bid_qty * bid, ask_qty * ask) < self._book_min_depth_quote
                ):
                    return LiveExecutionResult(
                        status="blocked",
                        reason="no_trade_zone",
                        order={
                            "pair": pair,
                            "side": side,
                            "spread_bps": spread_bps,
                            "bid_qty": bid_qty,
                            "ask_qty": ask_qty,
                            "depth_quote": min(bid_qty * bid, ask_qty * ask),
                            "min_depth_quote": self._book_min_depth_quote,
                        },
                    )
                fill_ok, fill_diag = self._expected_fill_probability_allows(
                    pair=pair,
                    bid=bid,
                    ask=ask,
                    bid_qty=bid_qty,
                    ask_qty=ask_qty,
                    spread_bps=spread_bps,
                )
                if not fill_ok and not is_probe:
                    return LiveExecutionResult(
                        status="blocked",
                        reason="expected_fill_probability_low",
                        order={"pair": pair, "side": side, **fill_diag},
                    )
                ms_ok, ms_reason = self._entry_allowed_by_microstructure(side, micro)
                if not ms_ok:
                    if not is_probe:
                        return LiveExecutionResult(
                            status="blocked",
                            reason=ms_reason,
                            order={
                                "pair": pair,
                                "side": side,
                                "imbalance": float(micro.get("imbalance", 0.0)),
                                "microprice": float(micro.get("microprice", 0.0)),
                            },
                        )
                edge_ok, edge_diag = self._fee_aware_entry_allows(intent, spread_bps, slippage_for_gate)
                if not edge_ok:
                    if not is_probe:
                        return LiveExecutionResult(
                            status="blocked",
                            reason="fee_aware_no_edge",
                            order={"pair": pair, "side": side, **edge_diag},
                        )
        except Exception as exc:
            return self._reject_guard(exc)

        target_notional = max(0.0, float(intent.target_notional))
        target_notional *= float(vol_adjust.get("notional_scale", 1.0) or 1.0)
        if side == "buy" and self._position_age_escalation_enabled:
            oldest_age = 0.0
            now_ref = time.time()
            for ledger_i in self._ledgers.values():
                if ledger_i.position_qty <= 0.0 or ledger_i.position_open_ts is None:
                    continue
                oldest_age = max(oldest_age, max(0.0, now_ref - float(ledger_i.position_open_ts)))
            if oldest_age >= self._position_age_escalation_s:
                target_notional *= self._position_age_entry_scale
        if side == "buy" and self._inventory_throttle_enabled and ask > 0.0:
            ledger_here = self._ledger_for(pair)
            inv_notional = max(0.0, float(ledger_here.position_qty) * float(ask))
            if inv_notional >= self._inventory_max_notional_quote:
                self._record_probe_result(is_probe=is_probe, success=False, reason="inventory_throttle_max")
                return LiveExecutionResult(
                    status="blocked",
                    reason="inventory_throttle_max",
                    order={
                        "pair": pair,
                        "side": side,
                        "inventory_notional_quote": inv_notional,
                        "inventory_max_notional_quote": self._inventory_max_notional_quote,
                    },
                )
            if inv_notional > self._inventory_target_notional_quote:
                span = max(1e-9, self._inventory_max_notional_quote - self._inventory_target_notional_quote)
                pressure = min(1.0, max(0.0, (inv_notional - self._inventory_target_notional_quote) / span))
                scale = max(0.05, 1.0 - (pressure * self._inventory_throttle_step))
                target_notional *= scale
        quote_reserve = min(0.999, max(0.5, float(os.getenv("AUTONOMOUS_QUOTE_RESERVE_RATIO", "0.985") or "0.985")))
        if is_probe:
            probe_quote_reserve = float(os.getenv("AUTONOMOUS_PROBE_QUOTE_RESERVE_RATIO", str(quote_reserve)) or quote_reserve)
            quote_reserve = min(1.0, max(0.0, probe_quote_reserve))
        # Keep a fee/safety reserve from free quote balance.
        quote_usable = max(0.0, available_quote * quote_reserve)
        meta = self.min_guard.pair_meta(pair)
        costmin = float(meta.get("costmin", 0.0) or 0.0)
        min_order_base = float(meta.get("ordermin", 0.0) or 0.0)
        available_base_effective = float(available_base)
        if side == "buy":
            min_required_quote = min_order_base * ask
            effective_min_quote = max(costmin, min_required_quote)
            quote_min_buffer_env = (
                os.getenv("AUTONOMOUS_PROBE_QUOTE_MIN_BUFFER_MULT", "1.0")
                if is_probe
                else os.getenv("AUTONOMOUS_QUOTE_MIN_BUFFER_MULT", "1.02")
            )
            quote_min_buffer_mult = max(0.9 if is_probe else 1.0, float(quote_min_buffer_env or "1.0"))
            constraints = self.min_guard.constraint_snapshot(pair, ask)
            if quote_usable <= 0:
                return LiveExecutionResult(
                    status="blocked",
                    reason="insufficient_balance_block",
                    order={
                        "pair": pair,
                        "side": side,
                        "available_quote": available_quote,
                        "quote_ccy": quote_ccy,
                        "exchange_constraints": constraints,
                    },
                )
            buffered_min_quote = effective_min_quote * quote_min_buffer_mult
            if effective_min_quote > 0 and quote_usable < buffered_min_quote:
                return LiveExecutionResult(
                    status="blocked",
                    reason="insufficient_balance_block",
                    order={
                        "pair": pair,
                        "side": side,
                        "available_quote": available_quote,
                        "quote_ccy": quote_ccy,
                        "min_required_quote": buffered_min_quote,
                        "exchange_constraints": constraints,
                    },
                )
            if effective_min_quote > 0 and target_notional < effective_min_quote:
                target_notional = effective_min_quote
            target_notional = min(target_notional, quote_usable)
            ok_v, val_or_reason = self.constraints_oracle.validate_and_round_order(
                symbol=pair,
                side=side,
                notional_quote=target_notional,
                bid=bid,
                ask=ask,
                order_type="market",
                max_quote_notional=quote_usable,
            )
            if not ok_v:
                return LiveExecutionResult(
                    status="blocked",
                    reason=str(val_or_reason),
                    order={
                        "pair": pair,
                        "side": side,
                        "target_notional": target_notional,
                        "available_quote": available_quote,
                        "quote_ccy": quote_ccy,
                        "exchange_constraints": self.min_guard.constraint_snapshot(pair, ask),
                    },
                )
            validated = val_or_reason
            assert not isinstance(validated, str)
            price = float(validated.rounded_price)
            vol = float(validated.rounded_qty)
            target_notional = float(validated.rounded_notional_quote)
            available_quote_check = quote_usable
        else:
            constraints = self.min_guard.constraint_snapshot(pair, bid)
            available_base_effective = max(0.0, available_base * self._sell_balance_buffer)
            sellable_quote = max(0.0, available_base_effective * bid)
            exchange_min_quote = max(0.0, float(constraints.get("min_notional_quote", 0.0) or 0.0))
            if available_base_effective <= 0:
                return LiveExecutionResult(
                    status="skipped",
                    reason="insufficient_base_balance_block",
                    order={
                        "pair": pair,
                        "side": side,
                        "available_base": available_base,
                        "available_base_effective": available_base_effective,
                        "base_ccy": base_ccy,
                        "execution_mode": "skip",
                        "exchange_constraints": constraints,
                    },
                )
            desired_profit_gate_qty = available_base_effective
            if not self._sell_all_in_on_profit and bid > 0.0:
                desired_profit_gate_qty = min(available_base_effective, max(0.0, target_notional / bid))
                if desired_profit_gate_qty <= 0.0:
                    desired_profit_gate_qty = available_base_effective
            profit_lock_block, profit_lock_details = self._sell_profit_lock_violation(
                pair=pair,
                bid=bid,
                ask=ask,
                intent=intent,
                target_exit_qty=desired_profit_gate_qty,
                slippage_bps_override=slippage_for_gate,
            )
            if profit_lock_block:
                return LiveExecutionResult(
                    status="skipped",
                    reason="profit_lock_sell_below_entry",
                    order={
                        "pair": pair,
                        "side": side,
                        "available_base": available_base,
                        "available_base_effective": available_base_effective,
                        "base_ccy": base_ccy,
                        "sellable_quote": sellable_quote,
                        "execution_mode": "skip",
                        "slippage_bps_used": slippage_for_gate,
                        **profit_lock_details,
                    },
                )
            gate_details_for_sell = dict(profit_lock_details)
            eligible_qty = float(profit_lock_details.get("eligible_qty", 0.0) or 0.0)
            if bool(profit_lock_details.get("profit_lock_partial_reduce", False)) and eligible_qty > 0.0:
                available_base_effective = min(available_base_effective, eligible_qty)
                sellable_quote = max(0.0, available_base_effective * bid)
                target_notional = min(max(0.0, target_notional), sellable_quote)
            if min_order_base > 0 and available_base_effective < min_order_base:
                self._mark_dust(base_ccy)
                return LiveExecutionResult(
                    status="skipped",
                    reason="inventory_below_min_order",
                    order={
                        "pair": pair,
                        "side": side,
                        "available_base": available_base,
                        "available_base_effective": available_base_effective,
                        "base_ccy": base_ccy,
                        "sellable_quote": sellable_quote,
                        "min_required_base": min_order_base,
                        "execution_mode": "skip",
                        "exchange_constraints": constraints,
                    },
                )
            base_max_notional = max(0.0, available_base_effective * bid)
            min_required_quote = min_order_base * bid
            effective_min_quote = max(costmin, min_required_quote)
            sell_min_notional_quote = max(effective_min_quote, exchange_min_quote)
            if sellable_quote < sell_min_notional_quote:
                self._mark_dust(base_ccy)
                return LiveExecutionResult(
                    status="skipped",
                    reason="inventory_below_min_order",
                    order={
                        "pair": pair,
                        "side": side,
                        "available_base": available_base,
                        "available_base_effective": available_base_effective,
                        "base_ccy": base_ccy,
                        "sellable_quote": sellable_quote,
                        "min_required_quote": sell_min_notional_quote,
                        "execution_mode": "skip",
                        "exchange_constraints": constraints,
                    },
                )
            if self._sell_all_in_on_profit:
                target_notional = base_max_notional
            if effective_min_quote > 0 and target_notional < effective_min_quote:
                if base_max_notional < effective_min_quote:
                    self._mark_dust(base_ccy)
                    return LiveExecutionResult(
                        status="skipped",
                        reason="inventory_below_min_order",
                        order={
                            "pair": pair,
                            "side": side,
                            "available_base": available_base,
                            "base_ccy": base_ccy,
                            "sellable_quote": sellable_quote,
                            "min_required_base": min_order_base,
                            "min_required_quote": effective_min_quote,
                            "execution_mode": "skip",
                            "exchange_constraints": constraints,
                        },
                    )
                target_notional = effective_min_quote
            target_notional = min(target_notional, base_max_notional)
            ok_v, val_or_reason = self.constraints_oracle.validate_and_round_order(
                symbol=pair,
                side=side,
                notional_quote=target_notional,
                bid=bid,
                ask=ask,
                order_type="market",
                max_quote_notional=base_max_notional,
            )
            if not ok_v:
                return LiveExecutionResult(
                    status="blocked",
                    reason=str(val_or_reason),
                    order={
                        "pair": pair,
                        "side": side,
                        "target_notional": target_notional,
                        "available_base": available_base,
                        "available_base_effective": available_base_effective,
                        "base_ccy": base_ccy,
                        "exchange_constraints": self.min_guard.constraint_snapshot(pair, bid),
                    },
                )
            validated = val_or_reason
            assert not isinstance(validated, str)
            price = float(validated.rounded_price)
            vol = min(float(validated.rounded_qty), max(0.0, available_base_effective))
            target_notional = float(vol * price)
            available_quote_check = float("inf")

        ok, guard_reason = self.min_guard.validate(
            pair,
            vol,
            price,
            available_quote_check,
            side=side,
            available_base=available_base,
        )
        if not ok:
            return LiveExecutionResult(
                status="blocked",
                reason=guard_reason,
                order={
                    "pair": pair,
                    "side": side,
                    "volume": vol,
                    "price": price,
                    "target_notional": target_notional,
                    "available_quote": available_quote,
                    "available_base": available_base,
                    "available_base_effective": available_base_effective if side == "sell" else available_base,
                    "quote_ccy": quote_ccy,
                    "base_ccy": base_ccy,
                    "costmin_quote": costmin,
                    "exchange_constraints": self.min_guard.constraint_snapshot(pair, price),
                },
            )

        # Independent pre-trade guard before sending order to venue.
        ok_pre, pre_reason = self._pretrade_guard(
            pair=pair,
            side=side,
            target_notional=vol * max(price, 0.0),
            reference_price=price,
            available_quote=quote_usable,
            available_base=available_base,
        )
        if not ok_pre:
            return LiveExecutionResult(
                status="blocked",
                reason=pre_reason,
                order={
                    "pair": pair,
                    "side": side,
                    "volume": vol,
                    "price": price,
                    "notional": vol * price,
                    "available_quote": available_quote,
                    "available_base": available_base_effective if side == "sell" else available_base,
                },
            )

        ok_open_orders, open_reason = self._open_order_limits_allow(pair, side)
        if not ok_open_orders:
            return LiveExecutionResult(
                status="blocked",
                reason=open_reason,
                order={"pair": pair, "side": side},
            )

        if self.settings.execution.kraken_spot.dry_run_long_only:
            self._recent_ids[dedupe] = now
            return LiveExecutionResult(
                status="blocked",
                reason="spot_live_execution_dry_run",
                order={
                    "pair": pair,
                    "side": side,
                    "volume": vol,
                    "price": price,
                    "notional": vol * price,
                    "quote_ccy": quote_ccy,
                    "base_ccy": base_ccy,
                },
            )

        # Kraken expects userref within signed 32-bit integer range.
        userref_raw = int(hashlib.sha256(f"{self.run_id}|{pair}|{side}|{int(now)}".encode("utf-8")).hexdigest()[:8], 16)
        userref = (userref_raw % 2_147_483_647) or 1
        if side == "sell":
            base_order = {
                "pair": pair,
                "type": side,
                "volume": f"{vol:.8f}",
                "userref": str(userref),
            }
            return self._submit_profit_locked_sell(
                pair=pair,
                vol=vol,
                bid=bid,
                ask=ask,
                base_order=base_order,
                gate_details=gate_details_for_sell,
                dedupe=dedupe,
                now=now,
                base_ccy=base_ccy,
                slippage_bps=slippage_for_gate,
            )

        ladder_out = self._submit_entry_ladder(
            pair=pair,
            quote_usable=quote_usable,
            target_notional=target_notional,
            bid=bid,
            ask=ask,
            quote_ccy=quote_ccy,
            vol_adjust=vol_adjust,
            userref_seed=userref,
        )
        if ladder_out is not None:
            self._recent_ids[dedupe] = now
            return ladder_out

        maker_preference, execution_mode_reason = self._adaptive_maker_preference(intent, side, bid, ask)
        if side == "buy" and self._entry_maker_only:
            maker_preference = True
            execution_mode_reason = "entry_maker_only"
        maker_timeout_env = os.getenv("AUTONOMOUS_MAKER_TIMEOUT_S", str(self.settings.execution.maker_timeout_s))
        timeout_s = max(1, int(float(maker_timeout_env or self.settings.execution.maker_timeout_s)))
        maker_raw_price = bid if side == "buy" else ask
        maker_price = self.min_guard.round_price(pair, max(maker_raw_price, 0.0))
        tick = 10 ** (-max(0, int(self.min_guard.pair_meta(pair).get("pair_decimals", 8) or 8)))
        if side == "buy" and is_probe:
            probe_ticks_raw = why.get("probe_distance_ticks", self._probe_distance_ticks_default) if isinstance(why, dict) else self._probe_distance_ticks_default
            try:
                probe_ticks = max(1, int(float(probe_ticks_raw)))
            except Exception:
                probe_ticks = self._probe_distance_ticks_default
            maker_price = self.min_guard.round_price(pair, min(max(bid, 0.0) + (tick * float(probe_ticks)), max(0.0, ask - tick)))
        elif side == "buy" and self._entry_maker_only:
            maker_price = self.min_guard.round_price(pair, min(max(bid, 0.0) + tick, max(0.0, ask - tick)))
        base_order = {
            "pair": pair,
            "type": side,
            "volume": f"{vol:.8f}",
            "userref": str(userref),
        }
        allow_taker_fallback = self._taker_fallback_allowed(side) and not (side == "buy" and self._entry_maker_only)

        # Maker-first spot execution reduces modeled TCO. We only taker-fallback if edge still beats cost.
        if maker_preference and maker_price > 0:
            if time.time() < self.rate_limit_cooldown_until_s:
                return self._rate_limit_cooldown_result({"pair": pair, "stage": "maker_submit"})
            maker_params = {**base_order, "ordertype": "limit", "oflags": "post"}
            out: dict[str, Any] | Any = {}
            submit_ok = False
            maker_attempt_price = maker_price
            for _attempt in range(3 if (side == "buy" and self._entry_maker_only) else 1):
                maker_params["price"] = f"{maker_attempt_price:.8f}"
                try:
                    out = self._call_with_retry(lambda: self.connector.add_order(maker_params), "maker_submit")
                    submit_ok = True
                    maker_price = maker_attempt_price
                    break
                except Exception as exc:
                    if side == "buy" and self._entry_maker_only and self._is_post_only_reject(exc):
                        maker_attempt_price = self.min_guard.round_price(
                            pair,
                            min(max(bid, 0.0) + (tick * 2.0), max(0.0, ask - tick)),
                        )
                        continue
                    return self._reject_guard(exc, {"pair": pair, "volume": vol, "price": maker_price, "stage": "maker_submit", "request_sent": True})
            if not submit_ok:
                return LiveExecutionResult(
                    status="blocked",
                    reason="maker_submit_failed",
                    order={"pair": pair, "side": side, "request_sent": False},
                )

            txids = out.get("txid", []) if isinstance(out, dict) else []
            txid = txids[0] if isinstance(txids, list) and txids else ""
            self._register_order_attempt(pair, txid, side, maker_price, now)
            deadline = time.time() + timeout_s
            while txid and time.time() < deadline:
                try:
                    q = self.connector.query_orders(txid)
                    row = q.get(txid, {}) if isinstance(q, dict) else {}
                    status = str(row.get("status", "")).lower()
                    vol_exec = float(row.get("vol_exec", 0.0) or 0.0)
                    if status == "closed" and vol_exec > 0:
                        self._recent_ids[dedupe] = now
                        return LiveExecutionResult(
                            status="filled_maker",
                            reason="spot_order_filled_maker",
                            order={
                                "pair": pair,
                                "side": side,
                                "volume": vol,
                                "price": maker_price,
                                "notional": vol * maker_price,
                                "txid": txid,
                                "userref": userref,
                                "execution_mode": "maker",
                                "execution_mode_reason": execution_mode_reason,
                                "request_sent": True,
                                "raw": out,
                            },
                        )
                except KrakenConnectorError as exc:
                    if self._is_rate_limit_err(exc):
                        self._activate_rate_limit_cooldown()
                        return self._rate_limit_cooldown_result({"pair": pair, "stage": "maker_query", "txid": txid, "request_sent": True})
                    break
                time.sleep(0.25)
            try:
                self.sync_fill_ledger(pair, mark_price=maker_price)
            except Exception:
                pass
            if txid:
                if time.time() < self.rate_limit_cooldown_until_s:
                    return self._rate_limit_cooldown_result({"pair": pair, "stage": "maker_cancel", "txid": txid})
                try:
                    self._call_with_retry(lambda: self.connector.cancel_order(txid), "maker_cancel")
                except Exception as exc:
                    if self._is_rate_limit_err(exc):
                        return self._reject_guard(exc, {"pair": pair, "volume": vol, "price": maker_price, "stage": "maker_cancel", "request_sent": True})
            if not self._taker_fallback_edge_ok(intent):
                return LiveExecutionResult(status="timeout", reason="maker_timeout_edge_le_cost", order={"pair": pair, "volume": vol, "price": maker_price, "txid": txid, "request_sent": True})
            if not allow_taker_fallback:
                return LiveExecutionResult(
                    status="timeout",
                    reason="maker_timeout_entry_maker_only" if side == "buy" and self._entry_maker_only else "maker_timeout_taker_disabled",
                    order={
                        "pair": pair,
                        "side": side,
                        "volume": vol,
                        "price": maker_price,
                        "txid": txid,
                        "execution_mode": "maker",
                        "execution_mode_reason": execution_mode_reason,
                        "request_sent": True,
                    },
                )

        if not allow_taker_fallback:
            return LiveExecutionResult(
                status="blocked",
                reason="entry_maker_only_no_market" if side == "buy" and self._entry_maker_only else "taker_disabled",
                order={
                    "pair": pair,
                    "side": side,
                    "volume": vol,
                    "price": price,
                    "notional": vol * price,
                    "execution_mode": "blocked",
                    "execution_mode_reason": execution_mode_reason,
                },
            )

        if time.time() < self.rate_limit_cooldown_until_s:
            return self._rate_limit_cooldown_result({"pair": pair, "stage": "taker_submit"})
        params = {**base_order, "ordertype": "market"}
        try:
            out = self._call_with_retry(lambda: self.connector.add_order(params), "taker_submit")
        except Exception as exc:
            return self._reject_guard(exc, {"pair": pair, "volume": vol, "price": price, "stage": "taker_submit", "request_sent": True})

        self._recent_ids[dedupe] = now
        txids = out.get("txid", []) if isinstance(out, dict) else []
        txid = txids[0] if isinstance(txids, list) and txids else ""
        self._register_order_attempt(pair, txid, side, price, now)
        try:
            self.sync_fill_ledger(pair, mark_price=price)
        except Exception:
            pass
        return LiveExecutionResult(
            status="filled_taker_fallback" if maker_preference else "submitted",
            reason="spot_order_taker_fallback" if maker_preference else "spot_order_submitted",
            order={
                "pair": pair,
                "side": side,
                "volume": vol,
                "price": price,
                "notional": vol * price,
                "txid": txid,
                "userref": userref,
                "execution_mode": "taker",
                "execution_mode_reason": execution_mode_reason,
                "request_sent": True,
                "raw": out if isinstance(out, dict) else {"result": out},
            },
        )

    def reconcile_live_state(self, internal_exposure: float) -> tuple[bool, str]:
        tracked = sum(abs(l.position_qty * max(l.avg_entry_price, 0.0)) for l in self._ledgers.values())
        diff = abs(float(internal_exposure) - tracked)
        tolerance = max(1.0, tracked * 0.5, abs(float(internal_exposure)) * 0.5)
        ok = diff <= tolerance
        return ok, "ok" if ok else f"ledger_mismatch:{diff:.6f}"

    def request_kill(self, reason: str = "operator_kill") -> None:
        self.killed = True
        self.safe_mode = True
        self.kill_reason = reason
        cooldown = max(300.0, float(self._auto_recover_kill_min_cooldown_s))
        self.cooldown_until_s = max(self.cooldown_until_s, time.time() + cooldown)

    def flatten_all_positions(self) -> tuple[bool, str]:
        if self.killed is False:
            self.request_kill("emergency")
        if time.time() < self.rate_limit_cooldown_until_s:
            return False, "rate_limit_cooldown"
        try:
            self.connector.cancel_all()
        except Exception:
            pass
        bal = self.connector.balance()
        pairs = self.min_guard.load_pairs()
        quote_ccys = {"ZUSD", "USD", "USDT", "ZEUR", "EUR"}
        blocked = 0
        submitted = 0
        for asset, amount in bal.items() if isinstance(bal, dict) else []:
            if asset in quote_ccys:
                continue
            if self._is_asset_dust_ignored(str(asset)):
                continue
            qty = float(amount or 0.0)
            if qty <= 0:
                continue
            pair = next((p for p, m in pairs.items() if m.get("base") == asset and m.get("quote") in quote_ccys), "")
            if not pair:
                continue
            try:
                snap = self.market_snapshot(pair, force_refresh=True)
            except Exception:
                blocked += 1
                continue
            bid = float(snap.get("bid", 0.0) or 0.0)
            ask = float(snap.get("ask", 0.0) or 0.0)
            if bid <= 0.0 or ask <= 0.0 or bool(snap.get("stale", False)):
                blocked += 1
                continue
            vol = self._round_volume_down_to_step(pair, qty * self._sell_balance_buffer)
            if vol <= 0:
                self._mark_dust(asset)
                continue
            intent = _IntentView(
                symbol=pair,
                side="sell",
                target_notional=max(0.0, vol * bid),
                why={
                    "risk": {"decision_reason": "flatten_best_effort"},
                    "governance": {"decision_reason": "flatten", "decision_fatal": True},
                },
            )
            blocked_by_gate, gate_details = self._sell_profit_lock_violation(
                pair=pair,
                bid=bid,
                ask=ask,
                intent=intent,
                target_exit_qty=vol,
            )
            if blocked_by_gate:
                blocked += 1
                continue
            eligible_qty = float(gate_details.get("eligible_qty", 0.0) or 0.0)
            if bool(gate_details.get("profit_lock_partial_reduce", False)):
                if eligible_qty <= 0.0:
                    blocked += 1
                    continue
                vol = min(vol, self._round_volume_down_to_step(pair, eligible_qty))
            if vol <= 0.0:
                self._mark_dust(asset)
                blocked += 1
                continue
            # Recompute gate for the final exit size so required floor price
            # is aligned with the actual submitted quantity.
            blocked_recheck, gate_details_recheck = self._sell_profit_lock_violation(
                pair=pair,
                bid=bid,
                ask=ask,
                intent=intent,
                target_exit_qty=vol,
            )
            if blocked_recheck:
                blocked += 1
                continue
            gate_details = gate_details_recheck
            ok_guard, _reason = self.min_guard.validate(
                pair,
                vol,
                bid,
                available_quote=max(0.0, vol * bid),
                side="sell",
                available_base=qty,
            )
            if not ok_guard:
                blocked += 1
                continue
            floor_price = float(gate_details.get("min_sell_price", 0.0) or 0.0)
            if floor_price <= 0.0:
                blocked += 1
                continue
            if floor_price > bid:
                blocked += 1
                continue
            meta = self.min_guard.pair_meta(pair)
            pair_decimals = int(meta.get("pair_decimals", 8) or 8)
            tick = 10 ** (-max(0, pair_decimals))
            floor_price = math.ceil(floor_price / max(tick, 1e-12)) * tick
            floor_price = self.min_guard.round_price(pair, floor_price)
            if floor_price <= 0.0:
                blocked += 1
                continue
            invariant_ok, _invariant_reason = self._enforce_sell_profit_invariant(
                pair=pair,
                bid=bid,
                ask=ask,
                qty=vol,
                gate_details=gate_details,
                slippage_bps=self._slippage_bps_profit_gate,
            )
            if not invariant_ok:
                blocked += 1
                continue
            try:
                self.exit_order_manager.submit_sell_limit_floor(
                    pair=pair,
                    qty=vol,
                    floor_price=floor_price,
                    bid=bid,
                    extra_params=None,
                    stage="flatten_sell_submit",
                )
                submitted += 1
                time.sleep(0.2)
            except KrakenConnectorError:
                blocked += 1
                continue
        if submitted == 0 and blocked == 0:
            return True, "flat"
        if blocked > 0 and submitted == 0:
            return False, "profit_gate_block_open_positions"
        if blocked > 0:
            return False, "partial_flatten_profit_gate_block"
        return True, "flatten_best_effort"
