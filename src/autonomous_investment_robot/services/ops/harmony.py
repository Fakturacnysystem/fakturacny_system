from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from autonomous_investment_robot.config.settings import RobotSettings


def _as_float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    if out != out:  # NaN guard
        return float(default)
    return float(out)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return bool(default)
    txt = str(value).strip().lower()
    if txt in {"1", "true", "yes", "on"}:
        return True
    if txt in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _norm_guard_mode(value: Any, default: str = "strict") -> str:
    txt = str(value or default).strip().lower()
    if txt not in {"strict", "fatal_only"}:
        return str(default)
    return txt


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class HarmonyCollision:
    key: str
    winner: str
    losers: list[str]


@dataclass
class ResolvedHarmonyConfig:
    order_cadence_s: float
    guards_mode: str
    user_min_order_quote: float
    exchange_min_order_quote: float
    effective_min_order_quote: float
    sell_min_profit_bps: float
    sell_target_profit_bps: float
    tp_only_mode: bool
    max_orders_per_min: int
    market_watch_every_s: float
    market_watch_max_calls_per_min: int
    blackout_enabled: bool
    blackout_windows_present: bool
    spread_spike_enabled: bool
    spread_spike_mult: float
    spread_spike_min_bps: float
    spread_spike_edge_add_bps: float
    spread_spike_hold_s: float
    liquidity_map_enabled: bool
    freeze_contract_version: str = "phase23_resolved_harmony_v1"
    resolved_config_fingerprint: str = ""
    hard_sell_floor_bps: float = 30.0
    collisions: list[HarmonyCollision] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["collisions"] = [asdict(c) for c in self.collisions]
        return out


class HarmonyConfigResolver:
    """
    Single-source resolver that normalizes conflicting env knobs into one coherent runtime config.
    """

    _CADENCE_KEYS = (
        "AUTONOMOUS_MIN_SECONDS_BETWEEN_ORDERS",
        "AUTONOMOUS_TRADE_COOLDOWN_S",
        "ORDER_SUBMISSION_INTERVAL_SECONDS",
    )
    _MARKET_WATCH_KEYS = (
        "AUTONOMOUS_MARKET_WATCH_INTERVAL_S",
        "AUTONOMOUS_MARKET_WATCH_SECONDS",
    )

    def _pick(self, env: dict[str, str], key: str, default: Any) -> Any:
        if key in env and str(env[key]).strip():
            return env[key]
        val = os.getenv(key)
        if val is not None and str(val).strip():
            return val
        return default

    def _resolve_cadence(self, env: dict[str, str]) -> tuple[float, list[HarmonyCollision]]:
        collisions: list[HarmonyCollision] = []
        explicit = self._pick(env, "AUTONOMOUS_ORDER_CADENCE_S", None)
        if explicit is not None and str(explicit).strip():
            losers = [k for k in self._CADENCE_KEYS if self._pick(env, k, None) is not None]
            if losers:
                collisions.append(
                    HarmonyCollision(
                        key="order_cadence",
                        winner="AUTONOMOUS_ORDER_CADENCE_S",
                        losers=losers,
                    )
                )
            return max(1.0, _as_float(explicit, 60.0)), collisions

        legacy_values: dict[str, float] = {}
        for k in self._CADENCE_KEYS:
            raw = self._pick(env, k, None)
            if raw is None:
                continue
            legacy_values[k] = max(0.0, _as_float(raw, 0.0))
        if not legacy_values:
            return 60.0, collisions
        if len(set(round(v, 6) for v in legacy_values.values())) > 1:
            winner_key = max(legacy_values, key=lambda kk: legacy_values[kk])
            losers = [k for k in legacy_values if k != winner_key]
            collisions.append(
                HarmonyCollision(
                    key="order_cadence",
                    winner=winner_key,
                    losers=losers,
                )
            )
        cadence = max(legacy_values.values())
        return max(1.0, cadence), collisions

    def resolve(
        self,
        settings: RobotSettings,
        env_snapshot: dict[str, str] | None = None,
        *,
        exchange_min_quote_fallback: float,
        dry_run: bool = False,
    ) -> ResolvedHarmonyConfig:
        env = dict(env_snapshot or {})
        collisions: list[HarmonyCollision] = []
        cadence_s, cadence_collisions = self._resolve_cadence(env)
        collisions.extend(cadence_collisions)

        guards_mode = _norm_guard_mode(self._pick(env, "AUTONOMOUS_GUARDS_MODE", "strict"))
        user_min = max(0.0, _as_float(self._pick(env, "AUTONOMOUS_USER_MIN_ORDER_QUOTE", 2.0), 2.0))
        legacy_min = max(0.0, _as_float(self._pick(env, "AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE", 0.0), 0.0))
        if legacy_min > 0.0 and abs(legacy_min - user_min) > 1e-12:
            winner = "AUTONOMOUS_USER_MIN_ORDER_QUOTE" if user_min >= legacy_min else "AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE"
            losers = ["AUTONOMOUS_MIN_ORDER_NOTIONAL_QUOTE" if winner == "AUTONOMOUS_USER_MIN_ORDER_QUOTE" else "AUTONOMOUS_USER_MIN_ORDER_QUOTE"]
            collisions.append(HarmonyCollision(key="min_order_quote", winner=winner, losers=losers))
        exchange_min = max(
            0.0,
            _as_float(
                self._pick(
                    env,
                    "AUTONOMOUS_EXCHANGE_MIN_ORDER_QUOTE_FALLBACK",
                    exchange_min_quote_fallback,
                ),
                exchange_min_quote_fallback,
            ),
        )
        if not dry_run:
            exchange_min = max(0.0, float(exchange_min_quote_fallback))
        effective_min = max(exchange_min, user_min, legacy_min)

        hard_floor_bps = max(
            0.0,
            _as_float(
                self._pick(
                    env,
                    "AUTONOMOUS_SELL_HARD_MIN_PROFIT_BPS",
                    self._pick(env, "AUTONOMOUS_SPOT_SELL_HARD_FLOOR_BPS", 30.0),
                ),
                30.0,
            ),
        )
        explicit_min_net_bps = max(
            0.0,
            _as_float(
                self._pick(
                    env,
                    "AUTONOMOUS_SELL_MIN_NET_PROFIT_BPS",
                    self._pick(env, "AUTONOMOUS_SPOT_SELL_MIN_PROFIT_BPS", hard_floor_bps),
                ),
                hard_floor_bps,
            ),
        )
        profit_target_net = max(0.0, _as_float(self._pick(env, "AUTONOMOUS_PROFIT_TARGET_NET", 0.003), 0.003))
        modeled_floor = max(0.0, (2.0 * float(settings.execution.fee_bps)) + (2.0 * float(settings.execution.slippage_bps)))
        final_min_profit_bps = max(hard_floor_bps, explicit_min_net_bps, modeled_floor, profit_target_net * 10000.0)
        target_profit_bps = max(
            final_min_profit_bps,
            _as_float(self._pick(env, "AUTONOMOUS_SPOT_SELL_TARGET_PROFIT_BPS", 200.0), 200.0),
        )
        tp_only_mode = _as_bool(self._pick(env, "AUTONOMOUS_TP_ONLY_MODE", False), False)
        if "profit" in str(getattr(settings.storage, "run_dir", "") or "").lower():
            tp_only_mode = _as_bool(self._pick(env, "AUTONOMOUS_TP_ONLY_MODE", True), True)
        max_orders_per_min = max(1, _as_int(self._pick(env, "AUTONOMOUS_MAX_ORDERS_PER_MIN", 10), 10))
        explicit_market_watch = self._pick(env, "AUTONOMOUS_MARKET_WATCH_EVERY_S", None)
        legacy_market_watch = [k for k in self._MARKET_WATCH_KEYS if self._pick(env, k, None) is not None]
        if explicit_market_watch is not None and legacy_market_watch:
            collisions.append(
                HarmonyCollision(
                    key="market_watch_every_s",
                    winner="AUTONOMOUS_MARKET_WATCH_EVERY_S",
                    losers=list(legacy_market_watch),
                )
            )
        market_watch_every_s = max(
            5.0,
            _as_float(
                self._pick(
                    env,
                    "AUTONOMOUS_MARKET_WATCH_EVERY_S",
                    self._pick(env, "AUTONOMOUS_MARKET_WATCH_INTERVAL_S", 30.0),
                ),
                30.0,
            ),
        )
        market_watch_max_calls = max(
            1,
            _as_int(self._pick(env, "AUTONOMOUS_MARKET_WATCH_MAX_CALLS_PER_MIN", 60), 60),
        )
        blackout_raw = str(self._pick(env, "AUTONOMOUS_BLACKOUT_WINDOWS", "") or "").strip()
        blackout_enabled = _as_bool(self._pick(env, "AUTONOMOUS_BLACKOUT_ENABLED", True), True)
        spread_spike_enabled = _as_bool(self._pick(env, "AUTONOMOUS_SPREAD_SPIKE_ENABLED", True), True)
        liquidity_map_enabled = _as_bool(self._pick(env, "AUTONOMOUS_LIQUIDITY_MAP_ENABLED", True), True)

        resolved = ResolvedHarmonyConfig(
            order_cadence_s=float(cadence_s),
            guards_mode=guards_mode,
            user_min_order_quote=float(user_min),
            exchange_min_order_quote=float(exchange_min),
            effective_min_order_quote=float(effective_min),
            sell_min_profit_bps=float(final_min_profit_bps),
            sell_target_profit_bps=float(target_profit_bps),
            tp_only_mode=bool(tp_only_mode),
            max_orders_per_min=int(max_orders_per_min),
            market_watch_every_s=float(market_watch_every_s),
            market_watch_max_calls_per_min=int(market_watch_max_calls),
            blackout_enabled=bool(blackout_enabled),
            blackout_windows_present=bool(blackout_raw),
            spread_spike_enabled=bool(spread_spike_enabled),
            spread_spike_mult=max(1.0, _as_float(self._pick(env, "AUTONOMOUS_SPREAD_SPIKE_MULT", 2.5), 2.5)),
            spread_spike_min_bps=max(0.0, _as_float(self._pick(env, "AUTONOMOUS_SPREAD_SPIKE_MIN_BPS", 8.0), 8.0)),
            spread_spike_edge_add_bps=max(
                0.0,
                _as_float(self._pick(env, "AUTONOMOUS_SPREAD_SPIKE_EDGE_ADD_BPS", 6.0), 6.0),
            ),
            spread_spike_hold_s=max(1.0, _as_float(self._pick(env, "AUTONOMOUS_SPREAD_SPIKE_HOLD_S", 45.0), 45.0)),
            liquidity_map_enabled=bool(liquidity_map_enabled),
            hard_sell_floor_bps=float(hard_floor_bps),
            collisions=collisions,
        )
        fingerprint_payload = resolved.to_dict()
        fingerprint_payload.pop("resolved_config_fingerprint", None)
        resolved.resolved_config_fingerprint = _stable_hash(fingerprint_payload)
        return resolved

    def write_report(self, run_dir: str, resolved: ResolvedHarmonyConfig) -> str:
        out = Path(run_dir) / "harmony_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(resolved.to_dict(), sort_keys=True, indent=2), encoding="utf-8")
        return str(out)

    def resolve_from_config(
        self,
        config_path: str,
        *,
        env_snapshot: dict[str, str] | None = None,
        exchange_min_quote_fallback: float = 2.0,
        dry_run: bool = True,
    ) -> ResolvedHarmonyConfig:
        """Resolve harmony for an arbitrary config file (used by audit matrix tooling)."""

        settings = RobotSettings.from_file(config_path)
        return self.resolve(
            settings=settings,
            env_snapshot=env_snapshot or {},
            exchange_min_quote_fallback=exchange_min_quote_fallback,
            dry_run=dry_run,
        )
